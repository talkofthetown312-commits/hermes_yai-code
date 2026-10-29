#!/usr/bin/env python3
"""Run a separate, local-only Pocket bridge against the installed Hermes SDK.

This launcher never uses port 8766, never imports the user's Hermes profile,
and never permits cloud/provider fallback.  It is intentionally conservative:
an installed Ollama model is selectable only when available RAM clears a fixed
headroom check.  The normal Pocket bridge owns chat/file persistence in a new
state directory, while Hermes receives an isolated HERMES_HOME.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MARKER = "hermes-yai-phase4-local-only-v1"
FORBIDDEN_PORTS = {8766, 8877, 8893}


def available_mib() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0


def required_mib(model: str, models: dict[str, int]) -> int:
    """Reserve model expansion plus a fixed Android/Hermes headroom.

    The 2.5 GiB floor is the existing reviewed Qwen preflight.  A 9B model is
    additionally rejected below 12 GiB even if a server reports a misleading
    size.  This routine does not load or probe a model.
    """
    size = models.get(model)
    if size is None:
        return 2**31 - 1
    if "9b" in model.lower():
        return 12288
    return max(2560, (size * 3) // (2 * 1024 * 1024) + 512)


def prepare(directory: Path) -> tuple[Path, object]:
    directory = Path(os.path.abspath(directory))
    if directory.name.startswith(".") or directory == ROOT or directory.is_relative_to(ROOT):
        raise ValueError("Use a new private state directory outside source")
    if any(item.is_symlink() for item in (directory, *directory.parents)):
        raise ValueError("Symlink state directories are refused")
    owner = directory / "phase4-owner.json"
    if directory.exists():
        if not owner.is_file() or owner.is_symlink() or json.loads(owner.read_text()) != {"format": MARKER}:
            raise ValueError("Existing state directory is not owned by Phase 4")
    else:
        directory.mkdir(mode=0o700, parents=True)
        owner.write_text(json.dumps({"format": MARKER}))
        owner.chmod(0o600)
    directory.chmod(0o700)
    lock = (directory / "server.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    app = directory / "app" / "pocket"
    if not app.exists():
        app.mkdir(parents=True, mode=0o700)
        for source in (ROOT / "phase2" / "pocket").glob("*.py"):
            shutil.copyfile(source, app / source.name)
        shutil.copytree(ROOT / "phase2" / "pocket" / "web", app / "web")
        for name in ("schema-fixtures.json", "synthetic-reference.md", "skill-catalog.json"):
            shutil.copyfile(ROOT / "phase2" / name, app.parent / name)
    return app, lock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path.home() / "hermes-yai-phase4-local")
    parser.add_argument("--port", type=int, default=8894)
    options = parser.parse_args()
    if options.port in FORBIDDEN_PORTS or not 1024 <= options.port <= 65535:
        parser.error("Use an unused unprivileged staging port, never 8766/8877/8893")
    hermes = Path.home() / ".hermes" / "venv" / "bin" / "hermes"
    python = Path.home() / ".hermes" / "venv" / "bin" / "python3"
    if not hermes.is_file() or not python.is_file():
        parser.error("Installed Hermes virtual environment is unavailable")
    state, lock = prepare(options.state_dir)
    path = os.environ.get("PATH", "")
    os.environ.clear()
    os.environ.update({"PATH": path, "HOME": str(options.state_dir / "home"),
                       "HERMES_HOME": str(options.state_dir / "home" / "hermes"),
                       "TMPDIR": str(options.state_dir / "tmp"),
                       "HERMES_POCKET_DATA": str(options.state_dir / "app" / "data"),
                       "HERMES_POCKET_PORT": str(options.port), "HERMES_BIN": str(hermes),
                       "HERMES_POCKET_INSTALLED_HERMES": str(hermes),
                       "HERMES_POCKET_LIVE_STAGING": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    for name in ("home/hermes", "tmp"):
        (options.state_dir / name).mkdir(parents=True, mode=0o700, exist_ok=True)
    sys.path.insert(0, str(state))
    import bridge
    capability = bridge.probe()
    if capability.get("adapter") != "installed-hermes-sdk":
        raise RuntimeError("Installed Hermes SDK adapter was not verified; refusing native/cloud CLI fallback")
    bridge.CAPABILITY = {**capability, "cloud_allowed": False, "memory": "default-denied"}

    original_models = bridge.local_models
    def local_models():
        raw = original_models()
        try:
            from urllib.request import urlopen
            with urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
                entries = json.load(response).get("models", [])
            sizes = {item["name"]: int(item["size"]) for item in entries if isinstance(item.get("name"), str) and isinstance(item.get("size"), int)}
        except Exception:
            sizes = {}
        free = available_mib()
        raw["available_mib"] = free
        raw["safe_models"] = [name for name in raw.get("models", []) if free >= required_mib(name, sizes)]
        raw["safety"] = "local-only; models below RAM headroom are unavailable; no provider fallback"
        return raw
    bridge.local_models = local_models

    class Handler(bridge.Handler):
        def do_POST(self):
            path = urlsplit(self.path).path
            if path == "/api/chats":
                # Reject cloud before delegating to the generic bridge.  The
                # generic bridge still validates model membership and persists.
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(size))
                except (ValueError, json.JSONDecodeError):
                    return self.reply(400, {"error": "Invalid request"})
                if body.get("mode", "local") != "local":
                    return self.reply(403, {"error": "Cloud and paid providers are disabled in this staging bridge."})
                model = body.get("model", "")
                if model not in local_models().get("safe_models", []):
                    return self.reply(409, {"error": "This local model is unavailable until RAM headroom is safe. No fallback was attempted."})
                # Rebuild the request body for the inherited handler after our
                # bounded read.  BaseHTTPRequestHandler does not buffer it.
                encoded = json.dumps(body).encode()
                self.rfile = __import__("io").BytesIO(encoded)
                self.headers.replace_header("Content-Length", str(len(encoded)))
            return super().do_POST()

    with bridge.ThreadingHTTPServer(("127.0.0.1", options.port), Handler) as server:
        bridge.PORT = server.server_port
        (options.state_dir / "server.json").write_text(json.dumps({"pid": os.getpid(), "port": bridge.PORT, "format": MARKER, "local_only": True}))
        print(f"Phase 4 local-only staging ready: http://127.0.0.1:{bridge.PORT}/", flush=True)
        try:
            server.serve_forever()
        finally:
            lock.close()


if __name__ == "__main__":
    main()
