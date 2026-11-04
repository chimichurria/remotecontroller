# Protocolo de RemoteHub

JSON por WebSocket en `ws://IP:8765/ws`, versión `1`. Cada mensaje es un objeto con la clave `t` (tipo).

## Conexión

1. El cliente abre el WebSocket y manda **en menos de 5 segundos**:

   ```json
   {"t": "hello", "token": "…", "name": "Mi Watch", "role": "controller"}
   ```

   `role` es `controller` (manda órdenes: Watch, iPhone, control web) o `phone` (recibe órdenes de la compu: cámara, linterna, Atajos).
2. Si el token es correcto, el receptor responde:

   ```json
   {"t": "ready", "v": 1, "platform": "darwin", "presets": ["tests", "status", "review"]}
   ```

   `platform` es `darwin` (Mac) o `win32` (Windows). `presets` son los nombres de `[claude.presets]`.
3. Si no: `{"t": "error", "code": "auth"}` y se cierra. Tras 5 fallos desde la misma IP, durante 1 minuto responde `{"t": "error", "code": "locked"}`.

Antes del `hello` correcto no se ejecuta nada.

## Controlador → receptor

| `t` | Campos | Qué hace |
|---|---|---|
| `mouse.move` | `dx`, `dy` | Mueve el cursor (con sensibilidad y aceleración de `config.toml`) |
| `mouse.click` | `button` (`left`/`right`/`middle`), `count` (1 a 3) | Clic |
| `mouse.down` / `mouse.up` | `button` | Mantener y soltar (arrastrar) |
| `mouse.scroll` | `dx`, `dy` | Scroll |
| `media` | `action`: `play_pause` `next` `prev` `vol_up` `vol_down` `mute` `bright_up` `bright_down` | Multimedia (el brillo solo en Mac) |
| `slides` | `action`: `next` `prev` `start` `end` `black` | Presentaciones |
| `key.tap` | `key` | Una tecla (`enter`, `esc`, `left`, `a`…) |
| `key.combo` | `keys`: lista | Combinación. `mod` es Cmd en Mac y Ctrl en Windows. Alias: `["appswitch"]`, `["search"]` |
| `text.type` | `text` (hasta 2000), `enter` (opcional) | Escribe texto, por ejemplo dictado |
| `claude.run` | `text` (hasta 4000), `continue` (opcional) | Corre Claude Code headless |
| `claude.preset` | `name` | Corre un preset de `config.toml` |
| `claude.cancel` | | Cancela la ejecución en curso |
| `phone.cmd` | `action`, `name` (opcional) | Reenvía la orden a los iPhone conectados |
| `ping` | | Responde `{"t": "pong"}` |

`key.tap`, `key.combo` y `text.type` se rechazan si `allow_keys = false`. Los `claude.*` se rechazan si `allow_claude = false`.

## Receptor → controlador

| `t` | Campos | |
|---|---|---|
| `claude.output` | `id`, `chunk` | Texto que va llegando |
| `claude.done` | `id`, `ok`, `text` | Resultado final |
| `error` | `for`, `msg` | Falló un mensaje; la conexión sigue abierta |
| `pong` | | |

## Receptor → iPhone (`role: phone`)

`{"t": "phone.cmd", "action": "camera.shutter" | "torch" | "shortcut.run", "name": "…"}`

## HTTP

| Ruta | |
|---|---|
| `GET /` | Control web (sin secretos; el token viaja en el fragmento `#t=` del QR) |
| `GET /pair` | QR y token. **Solo desde la propia compu** (loopback y `Host` local) |
| `GET /health` | `{"ok": true}` |
| `POST /phone` | Con `Authorization: Bearer TOKEN` y `{"action": "…"}`, manda una orden al iPhone |

## Descubrimiento

El receptor se anuncia por Bonjour como `_remotehub._tcp` con las propiedades `v`, `platform`, `ip` y `port`.

## Deep link de la app de iPhone

`remotehub://IP:PUERTO?token=TOKEN`
