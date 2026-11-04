"""Tests del control web y del pairing SIN abrir sockets (corren en cualquier sandbox).

    python -m tests.test_web      (desde la carpeta receiver/)
"""
from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

from aiohttp.test_utils import make_mocked_request

from remotehub import webui
from remotehub.backends import DryRunBackend
from remotehub.config import Config, load_config
from remotehub.server import Hub, make_app

TOKEN = "TESTTOKEN123"
RECEIVER = Path(__file__).resolve().parent.parent


def req(path, remote="127.0.0.1", host="127.0.0.1:8765", app=None):
    tr = mock.Mock()
    tr.get_extra_info.side_effect = lambda k, d=None: (remote, 5555) if k == "peername" else d
    return make_mocked_request("GET", path, headers={"Host": host}, app=app, transport=tr)


async def main() -> None:
    hub = Hub(cfg=Config(), token=TOKEN, backend=DryRunBackend())
    app = make_app(hub)

    routes = {r.resource.canonical for r in app.router.routes() if r.method == "GET"}
    assert {"/", "/pair", "/ws", "/health", "/manifest.webmanifest"} <= routes, routes
    print("ok  rutas registradas")

    # /pair: solo loopback real y Host local (frena LAN y DNS rebinding)
    r = await webui.pair(req("/pair", app=app))
    assert r.status == 200 and TOKEN in r.text and "<svg" in r.text and "<?xml" not in r.text
    assert "no-store" in r.headers["Cache-Control"]
    for remote, host, why in [
        ("192.168.1.50", "192.168.1.9:8765", "otra IP de la LAN"),
        ("127.0.0.1", "evil.example.com", "Host ajeno (DNS rebinding)"),
        ("127.0.0.1", "192.168.1.9:8765", "Host con IP de la LAN"),
    ]:
        r = await webui.pair(req("/pair", remote=remote, host=host, app=app))
        assert r.status == 403 and TOKEN not in (r.text or ""), why
    print("ok  /pair solo desde la propia compu")

    # / no filtra el token y trae CSP
    handler = webui._static("index.html", "text/html", webui.INDEX_CSP)
    idx = await handler(req("/", app=app))
    assert idx.status == 200 and b"RemoteHub" in idx.body and TOKEN.encode() not in idx.body
    assert "script-src" in idx.headers["Content-Security-Policy"]
    for name, ctype in [("manifest.webmanifest", "application/manifest+json"),
                        ("icon-180.png", "image/png"), ("icon-512.png", "image/png")]:
        x = await webui._static(name, ctype)(req("/" + name, app=app))
        assert x.status == 200 and len(x.body) > 100, name
    print("ok  index sin secretos, con CSP; manifest e íconos")

    # allow_web = false => no hay control web ni /pair
    hub.cfg.allow_web = False
    off = {r.resource.canonical for r in make_app(hub).router.routes()}
    assert "/pair" not in off and "/" not in off
    hub.cfg.allow_web = True
    print("ok  allow_web=false desactiva el control web")

    # El control web habla el mismo protocolo que la app nativa
    sent: list[dict] = []

    class Fake:
        role, name = "controller", "t"

        async def send(self, obj):
            sent.append(obj)

    for m in [
        {"t": "mouse.move", "dx": 10, "dy": -4}, {"t": "mouse.click", "button": "right", "count": 1},
        {"t": "mouse.down", "button": "left"}, {"t": "mouse.up", "button": "left"},
        {"t": "mouse.scroll", "dx": 0, "dy": -2}, {"t": "slides", "action": "next"},
        {"t": "media", "action": "play_pause"}, {"t": "key.tap", "key": "backspace"},
        {"t": "key.combo", "keys": ["mod", "c"]}, {"t": "key.combo", "keys": ["appswitch"]},
        {"t": "text.type", "text": "hola", "enter": True},
    ]:
        await hub.handle(Fake(), m)
    kinds = [e[0] for e in hub.backend.log]
    assert kinds == ["move", "click", "down", "up", "scroll", "tap", "media", "tap",
                     "combo", "combo", "type", "tap"], kinds
    assert not sent, sent
    await hub.handle(Fake(), {"t": "nope"})
    assert sent and sent[0]["t"] == "error"
    print("ok  mensajes del control web llegan al backend")

    # config.toml se lee también en Python 3.9 / 3.10 (fallback a tomli)
    p = Path(tempfile.mkdtemp()) / "config.toml"
    p.write_text((RECEIVER / "config.example.toml").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.port == 8765 and cfg.allow_web and set(cfg.claude.presets) == {"tests", "status", "review"}
    print(f"ok  config.toml cargado en Python {sys.version_info.major}.{sys.version_info.minor}")

    # El control web no carga nada de afuera (funciona sin internet, en la LAN)
    html = (webui.WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"(src|href)=[\"']https?://", html), "el control web no debe cargar nada externo"
    print("ok  control web sin dependencias externas")

    print("\nTODO OK")


if __name__ == "__main__":
    asyncio.run(main())
