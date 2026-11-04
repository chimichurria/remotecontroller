"""Punto de entrada para PyInstaller (los imports relativos de __main__ no sirven como script)."""
import sys

from remotehub.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
