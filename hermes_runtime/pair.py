"""Generate a private local pairing QR; never send its token to a QR service."""
import argparse
import os
from pathlib import Path
import re


def pairing_url(token, port):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,100}', token):
        raise ValueError('Invalid pairing token')
    if type(port) is not int or not 1 <= port <= 65535 or port in {8766, 8877}:
        raise ValueError('Use the development runtime port')
    return f'http://127.0.0.1:{port}/#pair={token}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18877)
    args = parser.parse_args()
    token_file = args.data / 'pairing-token'
    if any(p.is_symlink() for p in (token_file, *token_file.parents)):
        parser.error('Symlink token path refused')
    token = token_file.read_text().strip()
    url = pairing_url(token, args.port)
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        parser.error('Install the optional dependency from requirements-runtime.txt')
    output = args.data / 'pairing-qr.svg'
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        qrcode.make(url, image_factory=SvgPathImage).save(stream)
    print('Private pairing QR saved inside the runtime directory as pairing-qr.svg.')
    print('It connects only on the device running the backend. Do not share it.')


if __name__ == '__main__':
    main()
