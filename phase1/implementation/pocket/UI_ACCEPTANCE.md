# Pocket full interface acceptance

Scope: existing native WebView + authenticated loopback Python bridge + installed Hermes runtime. Preserve token, signing identity, conversations, provider credentials and global Hermes config. No remote publication. Source backup exists privately outside the project.

Required gates before delivery:
1. Native system document picker supports multiple files; no blanket storage/camera permissions, no JavascriptInterface, no external navigation.
2. Authenticated, same-origin, bounded uploads stored privately under random IDs; chat ownership checked; filename traversal, symlinks, unsupported files, malformed base64 and quota overflow rejected. No unauthed upload/preview/export.
3. Composer attachment cards include image/text preview and remove; upload failure retains composer; send records exact attachment IDs. Cloud disclosure requires confirmation before sending selected content. Local does not route images to cloud.
4. Text/PDF/DOCX/XLSX attachment content reaches Hermes with truncation/errors explicit; native images use installed native image routing only when supported. No silent OCR/auxiliary cloud route. Small local model limitations remain visible.
5. Real tool start/complete callbacks record bounded arguments/results; progress labels distinguish completed/blocked/incomplete. Plain-text DOM rendering; previews never execute uploaded HTML/SVG.
6. Copy message/results, share and save message/conversation/attachments/generated workspace files. Native SAF save and grant-scoped cache-file share; browser fallback explicit. Never arbitrary filesystem HTTP download.
7. Regression, negative API/security, frontend behavior and artifact checks pass. Live test uses synthetic content only. Device picker/render/share/save tests reported separately if no ADB/device automation.
8. Rebuild version 0.2.0/code 2 with retained key; verify signature, lint, permissions, key continuity, archive integrity; deliver a new filename without replacing old installer.

Out of scope: voice recording, an interactive dangerous-command approval flow, offline vision, guarantees of local 1B tool reliability, automatic background startup.
