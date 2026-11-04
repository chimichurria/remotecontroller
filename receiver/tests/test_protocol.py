"""Test de punta a punta con cliente WebSocket real, backend dry-run y un 'claude' falso.

    python -m tests.test_protocol      (desde la carpeta receiver/)
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

import aiohttp
from aiohttp import web

from remotehub.backends import DryRunBackend, normalize_key
from remotehub.config import Config
from remotehub.server import Hub, make_app

TOKEN = "test-token-123"

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"type": "system", "subtype": "init"}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hola "}]}}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "mundo"}]}}), flush=True)
print(json.dumps({"type": "result", "result": "hola mundo", "args": sys.argv[1:]}), flush=True)
"""


async def recv(ws, t, timeout=3):
    while True:
        m = await asyncio.wait_for(ws.receive_json(), timeout)
        if m.get("t") == t:
            return m


async def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    if sys.platform == "win32":  # CreateProcess no ejecuta scripts sueltos: .py + wrapper .cmd
        (tmp / "fakeclaude.py").write_text(FAKE_CLAUDE)
        fake = tmp / "fakeclaude.cmd"
        fake.write_text(f'@"{sys.executable}" "%~dp0fakeclaude.py" %*\r\n')
    else:
        fake = tmp / "fakeclaude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    cfg = Config()
    cfg.sensitivity, cfg.accel = 1.0, 0.0
    cfg.claude.bin = str(fake)
    cfg.claude.cwd = str(tmp)
    backend = DryRunBackend()
    hub = Hub(cfg=cfg, token=TOKEN, backend=backend)

    runner = web.AppRunner(make_app(hub))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"127.0.0.1:{port}"

    async with aiohttp.ClientSession() as s:
        # 1. token malo => error auth + cierre
        async with s.ws_connect(f"http://{base}/ws") as ws:
            await ws.send_json({"t": "hello", "token": "mal", "name": "x"})
            assert (await recv(ws, "error"))["code"] == "auth"
        print("ok  auth rechaza token inválido")

        # 2. sin hello en 5 s => cierra (probamos con mensaje que no es hello)
        async with s.ws_connect(f"http://{base}/ws") as ws:
            await ws.send_json({"t": "mouse.move", "dx": 1, "dy": 1})
            assert (await recv(ws, "error"))["code"] == "auth"
        assert not backend.log, "no debe ejecutar nada sin autenticar"
        print("ok  nada se ejecuta antes del hello")

        # 3. controlador + teléfono
        async with s.ws_connect(f"http://{base}/ws") as ctl, s.ws_connect(f"http://{base}/ws") as ph:
            await ph.send_json({"t": "hello", "token": TOKEN, "name": "iPhone", "role": "phone"})
            await recv(ph, "ready")
            await ctl.send_json({"t": "hello", "token": TOKEN, "name": "Watch", "role": "controller"})
            ready = await recv(ctl, "ready")
            assert ready["v"] == 1
            assert "tests" in ready["presets"], ready

            await ctl.send_json({"t": "mouse.move", "dx": 10, "dy": -4})
            await ctl.send_json({"t": "mouse.click", "button": "right", "count": 1})
            await ctl.send_json({"t": "slides", "action": "next"})
            await ctl.send_json({"t": "slides", "action": "start"})
            await ctl.send_json({"t": "key.combo", "keys": ["mod", "c"]})
            await ctl.send_json({"t": "text.type", "text": "hola ñandú", "enter": True})
            await ctl.send_json({"t": "media", "action": "play_pause"})
            await ctl.send_json({"t": "ping"})
            await recv(ctl, "pong")
            kinds = [e[0] for e in backend.log]
            assert kinds == ["move", "click", "tap", "combo", "combo", "type", "tap", "media"], kinds
            assert backend.log[0] == ("move", 10, -4)
            assert backend.log[4][1][-1] == "c"
            print("ok  mouse / slides / teclas / dictado / media")

            await ctl.send_json({"t": "key.combo", "keys": ["appswitch"]})
            await ctl.send_json({"t": "ping"})
            await recv(ctl, "pong")
            assert backend.log[-1][0] == "combo" and backend.log[-1][1][-1] == "tab", backend.log[-1]
            print("ok  alias de combo 'appswitch' según sistema")

            # 4. mensaje inválido => error pero la conexión sigue viva
            await ctl.send_json({"t": "key.tap", "key": "tecla-inexistente"})
            assert (await recv(ctl, "error"))["for"] == "key.tap"
            await ctl.send_json({"t": "ping"})
            await recv(ctl, "pong")
            print("ok  errores no cierran la conexión")

            # 5. controlador -> teléfono, y HTTP -> teléfono
            await ctl.send_json({"t": "phone.cmd", "action": "camera.shutter"})
            assert (await recv(ph, "phone.cmd"))["action"] == "camera.shutter"
            async with s.post(f"http://{base}/phone", json={"action": "torch"},
                              headers={"Authorization": f"Bearer {TOKEN}"}) as r:
                assert (await r.json())["delivered"] == 1
            assert (await recv(ph, "phone.cmd"))["action"] == "torch"
            async with s.post(f"http://{base}/phone", json={"action": "torch"}) as r:
                assert r.status == 401
            print("ok  relé a iPhone (WS y HTTP) y HTTP sin token => 401")

            # 6. Claude Code (falso)
            await ctl.send_json({"t": "claude.run", "text": "decime hola"})
            done = await recv(ctl, "claude.done")
            assert done["ok"] and done["text"] == "hola mundo", done
            await ctl.send_json({"t": "claude.preset", "name": "tests"})
            assert (await recv(ctl, "claude.done"))["ok"]
            await ctl.send_json({"t": "claude.preset", "name": "no-existe"})
            assert (await recv(ctl, "error"))["for"] == "claude.preset"
            print("ok  claude.run / claude.preset (stream-json parseado)")

        # 6b. control web y pairing
        async with s.get(f"http://{base}/") as r:
            page = await r.text()
            assert r.status == 200 and "RemoteHub" in page and TOKEN not in page
        async with s.get(f"http://{base}/pair") as r:
            page = await r.text()
            assert r.status == 200 and TOKEN in page and "<svg" in page, r.status
        async with s.get(f"http://{base}/pair", headers={"Host": "evil.example.com"}) as r:
            assert r.status == 403 and TOKEN not in await r.text()
        async with s.get(f"http://{base}/manifest.webmanifest") as r:
            assert r.status == 200 and (await r.json(content_type=None))["name"] == "RemoteHub"
        print("ok  control web en /, /pair solo local (bloquea Host ajeno), manifest")

        # 7. flags de seguridad
        cfg.allow_keys = False
        async with s.ws_connect(f"http://{base}/ws") as ctl:
            await ctl.send_json({"t": "hello", "token": TOKEN, "name": "x"})
            await recv(ctl, "ready")
            n = len(backend.log)
            await ctl.send_json({"t": "text.type", "text": "no"})
            assert (await recv(ctl, "error"))["for"] == "text.type"
            assert len(backend.log) == n
        print("ok  allow_keys=false bloquea teclado")

        # 8. lockout tras 5 fallos
        for _ in range(5):
            async with s.ws_connect(f"http://{base}/ws") as ws:
                await ws.send_json({"t": "hello", "token": "mal"})
                await recv(ws, "error")
        async with s.ws_connect(f"http://{base}/ws") as ws:
            assert (await recv(ws, "error"))["code"] == "locked"
        print("ok  bloqueo por intentos fallidos")

    assert normalize_key("mod") in ("cmd", "ctrl")
    await runner.cleanup()
    print("\nTODO OK")


if __name__ == "__main__":
    asyncio.run(main())
