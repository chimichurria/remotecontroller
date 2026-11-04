# RemoteHub 🎛️

Controlá tu Mac o tu PC con Windows desde el celular, el iPhone o el Apple Watch

[![CI](https://github.com/chimichurria/remotecontroller/actions/workflows/ci.yml/badge.svg)](https://github.com/chimichurria/remotecontroller/actions/workflows/ci.yml)
[![iOS + watchOS](https://github.com/chimichurria/remotecontroller/actions/workflows/ios.yml/badge.svg)](https://github.com/chimichurria/remotecontroller/actions/workflows/ios.yml)

```
Apple Watch ──(Wi-Fi directo, o vía iPhone)──┐
Control web (cualquier celular) ──Wi-Fi──────┼──► Receptor (Mac / Windows) → mouse, teclado, slides, multimedia, Claude Code
iPhone (trackpad, teclas, dictado) ──Wi-Fi───┘
iPhone ◄── cámara, linterna, Atajos ◄── Watch / compu (CLI y HTTP)
```

## Descargas

Bajá lo que necesites de la [última versión](https://github.com/chimichurria/remotecontroller/releases/latest)

| Para | Archivo | Qué es |
|---|---|---|
| 🍎 Mac con chip Apple (M1 o más nuevo) | `RemoteHub-mac-arm64.zip` | Receptor |
| 🍎 Mac con Intel | `RemoteHub-mac-intel.zip` | Receptor |
| 🪟 Windows 10/11 | `RemoteHub-windows.zip` | Receptor |
| 📱 iPhone + ⌚ Watch | `RemoteHub-iPhone-Watch-unsigned.ipa` | App nativa, sin firmar (ver más abajo) |
| 📱 Cualquier celular | nada que descargar | Control web: se abre escaneando el QR |

Los instaladores de Mac y Windows **no están firmados**, así que el sistema avisa la primera vez (ver cada sección)

## 1. Receptor (en la compu que querés controlar)

### Mac
1. Descomprimí el zip y arrastrá `RemoteHub.app` a Aplicaciones
2. **Clic derecho → Abrir → Abrir** (solo la primera vez, por no estar firmada). Si dice que está dañada: `xattr -dr com.apple.quarantine /Applications/RemoteHub.app`
3. Cuando lo pida, andá a *Ajustes del Sistema → Privacidad y seguridad → Accesibilidad* y activá **RemoteHub** (y *Monitoreo de entrada* si aparece). Sin eso no se mueve el mouse
4. Se abre el navegador con el QR

### Windows
1. Descomprimí el zip y abrí `RemoteHub\RemoteHub.exe`
2. Si SmartScreen avisa: **Más información → Ejecutar de todas formas**
3. Aceptá el aviso del firewall para **redes privadas**
4. Se abre el navegador con el QR. La ventana negra es el receptor: cerrarla lo detiene

### Desde el código (Mac, Windows o Linux)
Necesita Python 3.9 o más nuevo

```bash
cd receiver
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m remotehub --open         # muestra IP, token y QR, y abre la página de pairing
```

- Probar sin tocar nada: `python -m remotehub --dry-run`
- Que arranque solo en Mac: `./install_macos_launchagent.sh`
- Config opcional: copiá `config.example.toml` a `~/Library/Application Support/remotehub/config.toml` (Mac) o `%APPDATA%\remotehub\config.toml` (Windows). **Cambiá `[claude] cwd`** a la carpeta de tu proyecto

## 2. Control web (cualquier celular, sin instalar nada)

1. Con el receptor andando, en la compu abrí `http://127.0.0.1:8765/pair`
2. Escaneá el QR de **Cualquier celular** con la cámara
3. Se abre el control en el navegador del celular. En iPhone: *Compartir → Agregar a pantalla de inicio* y queda como app

Trae mouse (trackpad), slides, teclas con dictado, atajos, multimedia y Claude. El celular y la compu tienen que estar en la misma red Wi-Fi

## 3. App de iPhone + Apple Watch

La app nativa suma lo que un navegador no puede: el **Watch** (mouse aéreo con giroscopio, doble toque, corona) y que el iPhone responda con cámara, linterna y Atajos

### Instalarla sin Mac ni Xcode
Con una cuenta de Apple gratuita, usando [Sideloadly](https://sideloadly.io) (Mac o Windows):

1. Conectá el iPhone por cable y abrí Sideloadly
2. Arrastrá `RemoteHub-iPhone-Watch-unsigned.ipa`
3. Poné tu Apple ID y tocá **Start**
4. En el iPhone: *Ajustes → General → VPN y administración de dispositivos* → confiá en tu Apple ID
5. Activá el **Modo desarrollador** (*Ajustes → Privacidad y seguridad*) y reiniciá si lo pide

Con Apple ID gratuito la app **caduca a los 7 días** y hay que reinstalarla. No se puede repartir a otras personas: para eso está el control web, o una cuenta paga de Apple Developer (US$99 al año) que habilita TestFlight

> ⚠️ Instalar la app del **Watch** por sideload es lo menos seguro: depende de que la herramienta firme también la app embebida. Si el Watch no aparece, usá el método de Xcode de abajo

### Compilarla con Xcode
Necesita Xcode 16+ y una cuenta de Apple Developer (la gratuita sirve)

```bash
brew install xcodegen
cd ios
# Editá project.yml: bundleIdPrefix, PRODUCT_BUNDLE_IDENTIFIER (x2), WKCompanionAppBundleIdentifier y DEVELOPMENT_TEAM
xcodegen
open RemoteHub.xcodeproj
```

Elegí tu iPhone como destino y dale Run. El Watch se instala solo desde la app Watch del iPhone

## 4. Conectar

1. Corré el receptor en la compu
2. Escaneá el QR con la **cámara del iPhone** (abre RemoteHub ya configurado) o con cualquier celular (abre el control web). Alternativa en la app: pestaña *Ajustes* → elegí la compu que aparece y pegá el token (`python -m remotehub token` lo muestra)
3. Abrí la app en el Watch. Arriba a la derecha dice `directo` (Wi-Fi) o `vía iPhone`

## Qué hace cada cosa

**iPhone / control web** — *Mouse*: 1 dedo mueve, 2 dedos scroll, tap click, tap con 2 dedos click derecho, tap y arrastrar. *Slides*, *Teclas* (dictado que se escribe en la compu, atajos, multimedia, brillo en Mac), *Claude* (presets y pedidos dictados). Solo la app: *iPhone* (cámara con disparador, linterna, Atajos)

**Watch** (deslizá hacia arriba o abajo entre pantallas)
- *Slides*: **doble toque** = siguiente (Series 9+, Ultra 2, watchOS 11), corona = adelante o atrás, **flick** de muñeca opcional
- *Mouse*: mouse aéreo con el giroscopio, doble toque = click, corona = scroll. Si un eje queda al revés, usá los switches de invertir
- *Multimedia*: doble toque = play o pausa, corona = volumen
- *Claude*: tocá el campo para dictar, o usá un preset. La respuesta aparece en el reloj
- *iPhone*: foto, linterna y Atajos en el celular

**Compu → iPhone**: `python -m remotehub phone camera.shutter` (también `torch`, `shortcut.run --name "Mi atajo"`)

**Ver y manejar el iPhone desde la Mac**: eso ya lo hace Apple con *iPhone Mirroring* (macOS 15+, iPhone bloqueado y cerca). No hace falta código

## Límites reales (de iOS, no del código)

- iOS no deja que una app mueva un cursor ni toque cosas en otras apps, así que "controlar el iPhone" son acciones concretas: cámara, linterna y Atajos
- Para recibir órdenes de la compu o del Watch, **la app del iPhone tiene que estar abierta** (mientras está conectada, la pantalla no se apaga). Los Atajos te llevan a la app Atajos y vuelven solos
- El mouse aéreo y el flick solo funcionan con la app del Watch en pantalla
- Sin Wi-Fi compartido no hay conexión directa. Para usarlo desde afuera de casa se puede sumar Tailscale (no incluido)

## Seguridad — leer

Quien tenga el token puede mover el mouse y teclear en tu compu, y eso equivale a controlarla. Por eso:

- Token aleatorio de 128 bits, comparación en tiempo constante, bloqueo de 1 minuto tras 5 intentos fallidos y nada se ejecuta antes de autenticar
- `/pair` (QR y token) **solo se abre desde la propia compu**; el control web no lleva el token en el HTML
- El tráfico va **sin cifrar** por la red local (`ws://`). Usalo solo en redes en las que confiás, no en Wi-Fi públicos
- Claude Code corre con `claude -p` y por defecto **solo puede leer** (`Read`, `Grep`, `Glob`). Para que edite o corra comandos hay que agregarlos a `allowed_tools` a conciencia, por ejemplo `"Bash(npm test:*)"`
- `allow_keys = false` desactiva teclado y dictado si solo querés mouse, slides y multimedia. `allow_web = false` apaga el control web

## Desarrollo

```bash
cd receiver
python -m tests.test_web        # control web, pairing y config (sin sockets)
python -m tests.test_protocol   # WebSocket real, backend simulado y un `claude` falso
```

El CI corre ambos en Ubuntu, Windows y macOS (Python 3.9 y 3.12) y compila la app de iPhone y Watch en cada cambio de `ios/`. Al subir un tag `v*` se arma el release con los instaladores. Lo que **no** está probado automáticamente: el mouse real en macOS y Windows y la CLI real de Claude Code

Protocolo: [PROTOCOL.md](PROTOCOL.md)

## Licencia

[MIT](LICENSE)
