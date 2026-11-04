#!/usr/bin/env bash
# Deja el receptor corriendo siempre en segundo plano en macOS (arranca al iniciar sesión).
# Uso:  ./install_macos_launchagent.sh        (desde la carpeta receiver/, con el venv ya creado)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"
PLIST="$HOME/Library/LaunchAgents/com.remotehub.receiver.plist"

[ -x "$PY" ] || { echo "No encuentro $PY. Creá el venv primero (ver README)."; exit 1; }

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.remotehub.receiver</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>-m</string><string>remotehub</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/remotehub.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/remotehub.log</string>
</dict></plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Listo. Log: ~/Library/Logs/remotehub.log"
echo "Token:  $PY -m remotehub token"
echo "Importante: dale permiso de Accesibilidad a $PY en Ajustes del Sistema > Privacidad y seguridad."
