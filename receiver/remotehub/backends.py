"""Backends de entrada: PynputBackend (real, Mac/Windows) y DryRunBackend (tests)."""
from __future__ import annotations

import subprocess
import sys

PLATFORM = sys.platform  # darwin | win32 | linux

# Teclas "con nombre". Cualquier otra cosa de 1 carácter se toma literal.
_NAMED = {
    "right": "right", "left": "left", "up": "up", "down": "down",
    "enter": "enter", "return": "enter", "esc": "esc", "escape": "esc",
    "tab": "tab", "space": "space", "backspace": "backspace", "delete": "delete",
    "home": "home", "end": "end", "pageup": "page_up", "pagedown": "page_down",
    "cmd": "cmd", "ctrl": "ctrl", "alt": "alt", "opt": "alt", "shift": "shift",
}
MOD = "cmd" if PLATFORM == "darwin" else "ctrl"

# Combos por defecto para "slides.start" (PowerPoint/Keynote/Google Slides).
DEFAULT_SLIDES_START = (
    ["cmd", "shift", "enter"] if PLATFORM == "darwin" else ["f5"]
)


# Combos con nombre que cambian según el sistema (el cliente manda ["appswitch"]).
COMBO_ALIASES = {
    "appswitch": ["cmd", "tab"] if PLATFORM == "darwin" else ["alt", "tab"],
    "search": ["cmd", "space"] if PLATFORM == "darwin" else ["cmd"],  # en Windows cmd = tecla Win
}


def expand_combo(keys: list[str]) -> list[str]:
    if len(keys) == 1 and str(keys[0]).lower() in COMBO_ALIASES:
        return list(COMBO_ALIASES[str(keys[0]).lower()])
    return list(keys)


def normalize_key(name: str) -> str:
    n = str(name).strip()
    low = n.lower()
    if low == "mod":
        return MOD
    if low in _NAMED:
        return _NAMED[low]
    if low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 20:
        return low
    if len(n) == 1:
        return n
    raise ValueError(f"tecla desconocida: {name!r}")


class DryRunBackend:
    """Registra las acciones en memoria; no toca el sistema."""

    def __init__(self) -> None:
        self.log: list[tuple] = []

    def move(self, dx, dy): self.log.append(("move", dx, dy))
    def click(self, button, count): self.log.append(("click", button, count))
    def press(self, button): self.log.append(("down", button))
    def release(self, button): self.log.append(("up", button))
    def scroll(self, dx, dy): self.log.append(("scroll", dx, dy))
    def tap(self, key): self.log.append(("tap", normalize_key(key)))
    def combo(self, keys): self.log.append(("combo", [normalize_key(k) for k in keys]))
    def type_text(self, text): self.log.append(("type", text))
    def media(self, action): self.log.append(("media", action))


class PynputBackend:
    def __init__(self) -> None:
        from pynput import keyboard, mouse  # import tardío: no existe en CI headless

        self._k = keyboard
        self._m = mouse
        self.kb = keyboard.Controller()
        self.ms = mouse.Controller()

    # --- mouse -----------------------------------------------------------
    def _btn(self, name: str):
        return {"left": self._m.Button.left, "right": self._m.Button.right,
                "middle": self._m.Button.middle}[name]

    def move(self, dx: int, dy: int) -> None:
        self.ms.move(dx, dy)

    def click(self, button: str, count: int) -> None:
        self.ms.click(self._btn(button), count)

    def press(self, button: str) -> None:
        self.ms.press(self._btn(button))

    def release(self, button: str) -> None:
        self.ms.release(self._btn(button))

    def scroll(self, dx: int, dy: int) -> None:
        self.ms.scroll(dx, dy)

    # --- teclado ---------------------------------------------------------
    def _key(self, name: str):
        n = normalize_key(name)
        if len(n) == 1:
            return n
        return getattr(self._k.Key, n)

    def tap(self, key: str) -> None:
        k = self._key(key)
        self.kb.press(k)
        self.kb.release(k)

    def combo(self, keys: list[str]) -> None:
        resolved = [self._key(k) for k in keys]
        for k in resolved:
            self.kb.press(k)
        for k in reversed(resolved):
            self.kb.release(k)

    def type_text(self, text: str) -> None:
        self.kb.type(text)

    # --- multimedia ------------------------------------------------------
    def media(self, action: str) -> None:
        K = self._k.Key
        keymap = {
            "play_pause": K.media_play_pause, "next": K.media_next,
            "prev": K.media_previous, "vol_up": K.media_volume_up,
            "vol_down": K.media_volume_down, "mute": K.media_volume_mute,
        }
        if action in keymap:
            self.kb.press(keymap[action])
            self.kb.release(keymap[action])
            return
        if action in ("bright_up", "bright_down"):
            if PLATFORM != "darwin":
                raise ValueError("el brillo solo está soportado en macOS")
            code = 144 if action == "bright_up" else 145
            subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to key code {code}'],
                check=False,
            )
            return
        raise ValueError(f"acción multimedia desconocida: {action!r}")
