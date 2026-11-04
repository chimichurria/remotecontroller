"""Corre Claude Code en modo headless (`claude -p`) y va devolviendo la salida."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Awaitable, Callable

from .config import ClaudeConfig

OnChunk = Callable[[str], Awaitable[None]]

# Una app abierta desde el Finder o el menú Inicio NO hereda el PATH de la terminal,
# así que `claude` (y `node`, del que depende) no se encontrarían. Buscamos en los
# lugares típicos de instalación.
EXTRA_DIRS = [
    "~/.local/bin", "~/.claude/local", "~/.npm-global/bin", "~/.volta/bin", "~/.bun/bin",
    "/opt/homebrew/bin", "/usr/local/bin", "%APPDATA%/npm", "%LOCALAPPDATA%/Programs/claude",
]


def _extra_path() -> str:
    dirs = (os.path.expanduser(os.path.expandvars(d)) for d in EXTRA_DIRS)
    return os.pathsep.join(d for d in dirs if "%" not in d and os.path.isdir(d))


def find_bin(name: str) -> str | None:
    """Ruta del ejecutable, buscando en el PATH y después en los lugares típicos."""
    found = shutil.which(name)
    if found or os.path.dirname(name):  # ruta explícita: no se busca en otro lado
        return found
    return shutil.which(name, path=_extra_path())


def child_env() -> dict[str, str]:
    """Entorno del proceso hijo con el PATH ampliado (claude suele ser un script de node)."""
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(p for p in (env.get("PATH", ""), _extra_path()) if p)
    return env


def build_args(cfg: ClaudeConfig, prompt: str, cont: bool) -> list[str]:
    # El prompt va justo después de -p: los flags variádicos (--allowedTools)
    # no se lo pueden tragar.
    args = [cfg.bin, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if cont:
        args.append("-c")
    if cfg.permission_mode and cfg.permission_mode != "default":
        args += ["--permission-mode", cfg.permission_mode]
    if cfg.allowed_tools:
        args += ["--allowedTools", ",".join(cfg.allowed_tools)]
    if cfg.max_turns:
        args += ["--max-turns", str(cfg.max_turns)]
    return args


def extract_text(line: str) -> tuple[str, str | None]:
    """Devuelve (chunk_para_mostrar, texto_final_si_es_result)."""
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return line, None
    if ev.get("type") == "assistant":
        parts = [
            b.get("text", "")
            for b in ev.get("message", {}).get("content", [])
            if b.get("type") == "text"
        ]
        return "".join(parts), None
    if ev.get("type") == "result":
        return "", str(ev.get("result", ""))
    return "", None


class ClaudeRunner:
    def __init__(self, cfg: ClaudeConfig) -> None:
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None

    @property
    def busy(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def run(self, prompt: str, cont: bool, on_chunk: OnChunk) -> tuple[bool, str]:
        if self.busy:
            return False, "Ya hay una ejecución en curso (cancelala primero)."
        exe = find_bin(self.cfg.bin)
        if exe is None:
            return False, (f"No encuentro '{self.cfg.bin}'. Instalá Claude Code o poné la ruta "
                           "completa en [claude] bin de config.toml.")
        args = build_args(self.cfg, prompt, cont)
        args[0] = exe
        self.proc = await asyncio.create_subprocess_exec(
            *args,
            env=child_env(),
            cwd=os.path.expanduser(self.cfg.cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
        final = ""
        seen: list[str] = []

        async def pump() -> None:
            nonlocal final
            assert self.proc and self.proc.stdout
            async for raw in self.proc.stdout:
                chunk, result = extract_text(raw.decode(errors="replace").strip())
                if chunk:
                    seen.append(chunk)
                    await on_chunk(chunk)
                if result is not None:
                    final = result

        try:
            await asyncio.wait_for(pump(), timeout=self.cfg.timeout)
            await self.proc.wait()
        except asyncio.TimeoutError:
            await self.cancel()
            return False, "Tiempo agotado."
        ok = self.proc.returncode == 0
        if not ok and not final:
            err = (await self.proc.stderr.read()).decode(errors="replace")[-500:] if self.proc.stderr else ""
            return False, err or f"claude terminó con código {self.proc.returncode}"
        return ok, final or "".join(seen)

    async def cancel(self) -> None:
        if self.busy and self.proc:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 3)
            except asyncio.TimeoutError:
                self.proc.kill()
