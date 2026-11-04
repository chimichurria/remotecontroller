"""Control web (cualquier celular o compu con navegador) y página de pairing.

- ``GET /``      control web; no contiene secretos, el token llega por el fragmento del QR
- ``GET /pair``  QR + token; SOLO desde la propia compu (loopback y Host local)
"""
from __future__ import annotations

import html
import io
import re
from pathlib import Path

from aiohttp import web

WEB_DIR = Path(__file__).parent / "web"
LOOPBACK_IPS = {"127.0.0.1", "::1"}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}

INDEX_CSP = (
    "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self' ws: wss:; manifest-src 'self'"
)
PAIR_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


def is_local_request(request: web.Request) -> bool:
    """Loopback real y Host local: frena DNS rebinding contra /pair."""
    if request.remote not in LOOPBACK_IPS:
        return False
    host = re.sub(r":\d+$", "", request.host or "")
    return host.lower() in LOCAL_HOSTS


def qr_svg(data: str) -> str:
    """QR como <svg> en línea (sin PIL). Vacío si falta el paquete qrcode."""
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        return ""
    img = qrcode.make(data, image_factory=SvgPathImage, border=2)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    return svg[svg.index("<svg"):]


PAIR_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RemoteHub · Conectar</title>
<style>
:root{{--bg:#f6f4ee;--fg:#1b1d1a;--card:#fff;--mut:#6a6f66;--ac:#2f7d3b;--bd:#dedbd0}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141612;--fg:#eceee8;--card:#1d201b;--mut:#9aa093;--ac:#6fcf7b;--bd:#2c3028}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;padding:24px 16px}}
main{{max-width:760px;margin:0 auto}}
h1{{font-size:28px;margin:0 0 4px}} p{{color:var(--mut);margin:0 0 20px}}
.grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:20px}}
.card h2{{font-size:18px;margin:0 0 4px}} .card p{{font-size:14px;margin:0 0 12px}}
.qr{{background:#fff;border-radius:12px;padding:8px}} .qr svg{{display:block;width:100%;height:auto}}
code{{display:block;word-break:break-all;background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;font:13px ui-monospace,Menlo,Consolas,monospace;margin-top:12px;user-select:all}}
.tok{{font-size:20px;letter-spacing:.5px;text-align:center}}
.warn{{margin-top:20px;font-size:13px;color:var(--mut)}}
</style></head><body><main>
<h1>RemoteHub 🎛️</h1>
<p>Escaneá un QR con tu celular para controlar esta compu ({platform}) desde {ip}:{port}</p>
<div class="grid">
<section class="card"><h2>📱 Cualquier celular</h2><p>Abre el control web en el navegador, sin instalar nada</p>
<div class="qr">{web_qr}</div><code>{web_url}</code></section>
<section class="card"><h2>🍎 App de iPhone y Watch</h2><p>Con la cámara del iPhone, abre RemoteHub ya configurado</p>
<div class="qr">{app_qr}</div><code>{app_url}</code></section>
</div>
<section class="card" style="margin-top:16px"><h2>🔑 Token</h2><p>Para pegarlo a mano en Ajustes de la app</p><code class="tok">{token}</code></section>
<p class="warn">Quien tenga este token controla tu compu. Mostralo solo en tu pantalla y usalo en redes de confianza</p>
</main></body></html>
"""


async def pair(request: web.Request) -> web.Response:
    if not is_local_request(request):
        return web.Response(status=403, text="Esta página solo se abre desde la propia compu")
    from .backends import PLATFORM
    from .server import lan_ip

    hub = request.app["hub"]
    port, token, ip = hub.cfg.port, hub.token, lan_ip()
    web_url = f"http://{ip}:{port}/#t={token}"
    app_url = f"remotehub://{ip}:{port}?token={token}"
    body = PAIR_PAGE.format(
        platform={"darwin": "Mac", "win32": "Windows"}.get(PLATFORM, PLATFORM),
        ip=html.escape(ip), port=port, token=html.escape(token),
        web_url=html.escape(web_url), app_url=html.escape(app_url),
        web_qr=qr_svg(web_url) or "<p>Instalá el paquete qrcode para ver el QR</p>",
        app_qr=qr_svg(app_url) or "<p>Instalá el paquete qrcode para ver el QR</p>",
    )
    return web.Response(
        text=body, content_type="text/html",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                 "Content-Security-Policy": PAIR_CSP, "X-Frame-Options": "DENY"},
    )


def _static(name: str, content_type: str, csp: str | None = None):
    path = WEB_DIR / name

    async def handler(_: web.Request) -> web.Response:
        if not path.exists():
            raise web.HTTPNotFound()
        headers = {"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"}
        if csp:
            headers["Content-Security-Policy"] = csp
        return web.Response(body=path.read_bytes(), content_type=content_type, headers=headers)

    return handler


def add_routes(app: web.Application) -> None:
    app.add_routes([
        web.get("/", _static("index.html", "text/html", INDEX_CSP)),
        web.get("/pair", pair),
        web.get("/manifest.webmanifest", _static("manifest.webmanifest", "application/manifest+json")),
        web.get("/icon-180.png", _static("icon-180.png", "image/png")),
        web.get("/icon-512.png", _static("icon-512.png", "image/png")),
    ])
