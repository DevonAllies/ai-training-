"""Tablet / phone access on your home network.

Off by default. When switched on (Settings), SimCoach listens on all network
interfaces so a tablet or phone on the same Wi-Fi can open the dashboard; the
Settings page shows the address and a QR code to scan.

Devices on the network get the coaching screens but cannot change settings,
quit/restart the app or delete anything - those stay limited to this PC.
"""

from __future__ import annotations

import io
import socket

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# Requests that only this PC may make (everything else is fine from a tablet).
_LOCAL_ONLY_POST = {"/api/config", "/api/quit", "/api/exit_demo", "/api/restart", "/api/voice/test"}


def is_local(host: str | None) -> bool:
    return (host or "") in LOCAL_HOSTS


def allowed_remote(method: str, path: str) -> bool:
    """May a device on the network make this request?"""
    if method == "DELETE":
        return False
    if method == "POST" and path in _LOCAL_ONLY_POST:
        return False
    return True


def lan_ips() -> list[str]:
    """This PC's addresses on the local network (best first)."""
    ips: list[str] = []
    try:                                  # the address used for the default route (no packet is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return [ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254.")]


def lan_urls(port: int) -> list[str]:
    urls = [f"http://{ip}:{port}/" for ip in lan_ips()]
    try:
        name = socket.gethostname()
        if name:
            urls.append(f"http://{name}:{port}/")
    except OSError:
        pass
    return urls


def qr_svg(text: str) -> str:
    """QR code as an SVG string (dark modules on a white quiet zone, scans in any theme)."""
    import qrcode
    import qrcode.image.svg
    qr = qrcode.QRCode(border=3, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathFillImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")
