"""Start CashUp as a shared LAN server for colleagues."""
from __future__ import annotations

import socket

from cashup import create_app

app = create_app()

PORT = 5000


def _lan_ips() -> list[str]:
    """Best-effort list of non-loopback IPv4 addresses on this machine."""
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith('127.') and ip not in found:
                found.append(ip)
    except OSError:
        pass

    if not found:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(('8.8.8.8', 80))
                ip = sock.getsockname()[0]
                if ip and not ip.startswith('127.'):
                    found.append(ip)
        except OSError:
            pass

    return found


def _print_urls() -> None:
    print()
    print('CashUp is running.')
    print(f'  On this PC:   http://127.0.0.1:{PORT}')
    for ip in _lan_ips():
        print(f'  For colleagues: http://{ip}:{PORT}')
    if not _lan_ips():
        print('  For colleagues: could not detect LAN IP — check Network settings.')
    print()
    print('Keep this window open while people are using CashUp.')
    print('Press Ctrl+C to stop.')
    print()


if __name__ == '__main__':
    _print_urls()
    # debug=False: safe for shared use. threaded=True: several people at once.
    app.run(debug=False, host='0.0.0.0', port=PORT, threaded=True)
