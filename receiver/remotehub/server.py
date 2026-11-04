"""Servidor RemoteHub: WebSocket + HTTP mínimo (aiohttp)."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import socket
import sys
import time
from dataclasses import dataclass, field

from aiohttp import WSMsgType, web

from .backends import DEFAULT_SLIDES_START, PLATFORM, expand_combo
from .claude_actions import ClaudeRunner
from .config import Config

log = logging.getLogger("remotehub")
PROTOCOL_VERSION = 1
MAX_FAILS = 5
LOCKOUT_SECONDS = 60


@dataclass(eq=False)
class Client:
    ws: web.WebSocketResponse
    name: str
    role: str
    peer: str = ""

    async def send(self, obj: dict) -> None:
        if not self.ws.closed:
            await self.ws.send_str(json.dumps(obj, ensure_ascii=False))


@dataclass
class Hub:
    cfg: Config
    token: str
    backend: object
    claude: ClaudeRunner = field(init=False)
    clients: set[Client] = field(default_factory=set)
    fails: dict[str, list[float]] = field(default_factory=dict)
    _rx: float = 0.0
    _ry: float = 0.0
    _claude_id: int = 0

    def __post_init__(self) -> None:
        self.claude = ClaudeRunner(self.cfg.claude)

    # ---- auth ------------------------------------------------------------
    def locked_out(self, ip: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self.fails.get(ip, []) if now - t < LOCKOUT_SECONDS]
        self.fails[ip] = recent
        return len(recent) >= MAX_FAILS

    def register_fail(self, ip: str) -> None:
        self.fails.setdefault(ip, []).append(time.monotonic())

    def check_token(self, candidate: str) -> bool:
        return hmac.compare_digest(str(candidate).encode(), self.token.encode())

    # ---- mouse con aceleración y resto sub-píxel --------------------------
    def _scaled(self, dx: float, dy: float) -> tuple[int, int]:
        speed = math.hypot(dx, dy)
        gain = self.cfg.sensitivity * (1 + self.cfg.accel * min(speed, 40) / 40)
        self._rx += dx * gain
        self._ry += dy * gain
        ix, iy = int(self._rx), int(self._ry)
        self._rx -= ix
        self._ry -= iy
        return ix, iy

    # ---- despacho --------------------------------------------------------
    async def handle(self, c: Client, msg: dict) -> None:
        t = msg.get("t", "")
        try:
            await self._handle(c, t, msg)
        except Exception as e:  # un mensaje malo nunca debe tirar la conexión
            log.warning("error en %s: %s", t, e)
            await c.send({"t": "error", "for": t, "msg": str(e)})

    async def _handle(self, c: Client, t: str, m: dict) -> None:
        b = self.backend
        if t == "mouse.move":
            ix, iy = self._scaled(float(m["dx"]), float(m["dy"]))
            if ix or iy:
                b.move(ix, iy)
        elif t == "mouse.click":
            b.click(m.get("button", "left"), max(1, min(3, int(m.get("count", 1)))))
        elif t == "mouse.down":
            b.press(m.get("button", "left"))
        elif t == "mouse.up":
            b.release(m.get("button", "left"))
        elif t == "mouse.scroll":
            s = self.cfg.scroll_sensitivity
            b.scroll(int(float(m.get("dx", 0)) * s), int(float(m.get("dy", 0)) * s))
        elif t == "media":
            b.media(m["action"])
        elif t == "slides":
            self._slides(m["action"])
        elif t in ("key.tap", "key.combo", "text.type"):
            if not self.cfg.allow_keys:
                raise PermissionError("teclado deshabilitado en config.toml (allow_keys)")
            if t == "key.tap":
                b.tap(m["key"])
            elif t == "key.combo":
                b.combo(expand_combo(list(m["keys"])))
            else:
                text = str(m["text"])[:2000]
                b.type_text(text)
                if m.get("enter"):
                    b.tap("enter")
        elif t in ("claude.run", "claude.preset", "claude.cancel"):
            if not self.cfg.allow_claude:
                raise PermissionError("Claude deshabilitado en config.toml (allow_claude)")
            await self._claude(c, t, m)
        elif t == "phone.cmd":
            await self.to_phones({k: v for k, v in m.items() if k != "t"})
        elif t == "ping":
            await c.send({"t": "pong"})
        else:
            raise ValueError(f"mensaje desconocido: {t!r}")

    def _slides(self, action: str) -> None:
        b = self.backend
        if action == "next":
            b.tap("right")
        elif action == "prev":
            b.tap("left")
        elif action == "start":
            b.combo(self.cfg.slides_start or DEFAULT_SLIDES_START)
        elif action == "end":
            b.tap("esc")
        elif action == "black":
            b.tap("b")
        else:
            raise ValueError(f"acción de slides desconocida: {action!r}")

    async def _claude(self, c: Client, t: str, m: dict) -> None:
        if t == "claude.cancel":
            await self.claude.cancel()
            return
        if t == "claude.preset":
            prompt = self.cfg.claude.presets.get(m["name"])
            if prompt is None:
                raise ValueError(f"preset inexistente: {m['name']!r}")
            cont = False
        else:
            prompt, cont = str(m["text"])[:4000], bool(m.get("continue"))
        self._claude_id += 1
        rid = self._claude_id

        async def on_chunk(chunk: str) -> None:
            await c.send({"t": "claude.output", "id": rid, "chunk": chunk})

        async def job() -> None:
            ok, text = await self.claude.run(prompt, cont, on_chunk)
            await c.send({"t": "claude.done", "id": rid, "ok": ok, "text": text})

        # No bloquea el loop del socket: se pueden seguir mandando mouse/teclas.
        asyncio.create_task(job())

    async def to_phones(self, payload: dict) -> int:
        phones = [p for p in self.clients if p.role == "phone"]
        for p in phones:
            await p.send({"t": "phone.cmd", **payload})
        return len(phones)


# ---- handlers HTTP/WS ---------------------------------------------------------
async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    hub: Hub = request.app["hub"]
    ip = request.remote or "?"
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=64 * 1024)
    await ws.prepare(request)

    if hub.locked_out(ip):
        await ws.send_str(json.dumps({"t": "error", "code": "locked"}))
        await ws.close()
        return ws

    client: Client | None = None
    try:
        first = await asyncio.wait_for(ws.receive(), timeout=5)
        hello = json.loads(first.data) if first.type == WSMsgType.TEXT else {}
        if hello.get("t") != "hello" or not hub.check_token(hello.get("token", "")):
            hub.register_fail(ip)
            await asyncio.sleep(0.5)
            await ws.send_str(json.dumps({"t": "error", "code": "auth"}))
            await ws.close()
            return ws
        role = "phone" if hello.get("role") == "phone" else "controller"
        client = Client(ws, str(hello.get("name", "cliente"))[:60], role, ip)
        hub.clients.add(client)
        log.info("conectado: %s (%s) desde %s", client.name, role, ip)
        await client.send({"t": "ready", "v": PROTOCOL_VERSION, "platform": PLATFORM,
                           "presets": list(hub.cfg.claude.presets)})

        async for raw in ws:
            if raw.type != WSMsgType.TEXT:
                continue
            try:
                msg = json.loads(raw.data)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                await hub.handle(client, msg)
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await ws.close()
    finally:
        if client:
            hub.clients.discard(client)
            log.info("desconectado: %s", client.name)
    return ws


async def phone_endpoint(request: web.Request) -> web.Response:
    hub: Hub = request.app["hub"]
    ip = request.remote or "?"
    if hub.locked_out(ip):
        return web.json_response({"error": "locked"}, status=429)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not hub.check_token(auth[7:]):
        hub.register_fail(ip)
        return web.json_response({"error": "auth"}, status=401)
    try:
        body = await request.json()
        action = str(body["action"])
    except Exception:
        return web.json_response({"error": "body inválido"}, status=400)
    delivered = await hub.to_phones({**body, "action": action})
    return web.json_response({"delivered": delivered})


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


def make_app(hub: Hub) -> web.Application:
    app = web.Application()
    app["hub"] = hub
    if hub.cfg.allow_web:
        from . import webui

        webui.add_routes(app)
    app.add_routes([
        web.get("/ws", ws_handler),
        web.post("/phone", phone_endpoint),
        web.get("/health", health),
    ])
    return app


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no envía nada; solo elige interfaz
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


async def advertise(port: int):
    """Anuncia el servicio por Bonjour. Devuelve el objeto para cerrarlo luego."""
    try:
        from zeroconf import IPVersion, ServiceInfo
        from zeroconf.asyncio import AsyncZeroconf
    except ImportError:
        log.warning("zeroconf no instalado: sin descubrimiento automático")
        return None
    ip = lan_ip()
    host = socket.gethostname().split(".")[0]
    info = ServiceInfo(
        "_remotehub._tcp.local.",
        f"RemoteHub {host}._remotehub._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"v": str(PROTOCOL_VERSION), "platform": PLATFORM, "ip": ip, "port": str(port)},
    )
    zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
    await zc.async_register_service(info)
    return zc, info
