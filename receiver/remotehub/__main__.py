"""Uso:
    python -m remotehub                # arranca el receptor
    python -m remotehub --dry-run      # sin tocar mouse/teclado (para probar)
    python -m remotehub --open         # además abre el QR de pairing en el navegador
    python -m remotehub phone camera.shutter   # dispara una acción en el iPhone
    python -m remotehub token          # muestra el token de pairing
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import urllib.request
import webbrowser

from aiohttp import web

from .backends import DryRunBackend
from .config import load_config, load_token
from .server import Hub, advertise, lan_ip, make_app


def cmd_phone(args: argparse.Namespace) -> int:
    cfg = load_config()
    body = {"action": args.action}
    if args.name:
        body["name"] = args.name
    req = urllib.request.Request(
        f"http://127.0.0.1:{cfg.port}/phone",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {load_token(create=False)}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        print(r.read().decode())
    return 0


def print_pairing(token: str, port: int) -> None:
    if sys.stdout is None:  # app empaquetada sin consola (Windows --noconsole)
        return
    ip = lan_ip()
    url = f"remotehub://{ip}:{port}?token={token}"
    print(f"\n  RemoteHub escuchando en {ip}:{port}")
    print(f"  Token de pairing: {token}")
    print(f"  Control web:      http://{ip}:{port}/#t={token}")
    print(f"  App de iPhone:    {url}")
    print(f"  QR para escanear (solo desde esta compu): http://127.0.0.1:{port}/pair")
    try:
        import qrcode  # opcional

        qr = qrcode.QRCode(border=1)
        qr.add_data(f"http://{ip}:{port}/#t={token}")
        qr.print_ascii(invert=True)
        print("  Escaneá el QR con la cámara de cualquier celular para abrir el control web.\n")
    except ImportError:
        print("  (pip install qrcode  →  muestra un QR para escanear con el celular)\n")


async def serve(dry_run: bool, open_browser: bool = False) -> None:
    cfg = load_config()
    token = load_token()
    if dry_run:
        backend = DryRunBackend()
    else:
        from .backends import PynputBackend

        backend = PynputBackend()
    hub = Hub(cfg=cfg, token=token, backend=backend)
    runner = web.AppRunner(make_app(hub))
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    zc = await advertise(cfg.port)
    print_pairing(token, cfg.port)
    if open_browser and cfg.allow_web:
        webbrowser.open(f"http://127.0.0.1:{cfg.port}/pair")
    if dry_run:
        print("  [dry-run] no se mueve el mouse ni se teclea nada.\n")
    try:
        await asyncio.Event().wait()
    finally:
        if zc:
            await zc[0].async_unregister_service(zc[1])
            await zc[0].async_close()
        await runner.cleanup()


def main() -> int:
    p = argparse.ArgumentParser(prog="remotehub")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--open", action="store_true", help="abre la página de pairing (QR) en el navegador")
    p.add_argument("--no-open", action="store_true", help="no abre el navegador (aunque sea la app empaquetada)")
    sub = p.add_subparsers(dest="cmd")
    ph = sub.add_parser("phone", help="disparar una acción en el iPhone")
    ph.add_argument("action", help="camera.shutter | torch | shortcut.run")
    ph.add_argument("--name", help="nombre del Atajo (shortcut.run)")
    sub.add_parser("token", help="mostrar el token de pairing")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.cmd == "phone":
        return cmd_phone(args)
    if args.cmd == "token":
        print(load_token())
        return 0
    try:
        frozen = bool(getattr(sys, "frozen", False))  # app empaquetada: abre el QR sola
        asyncio.run(serve(args.dry_run, args.open or (frozen and not args.no_open)))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
