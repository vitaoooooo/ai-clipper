#!/usr/bin/env python3
"""Atalho para continuar rodando `python clipador.py ...` sem instalar o pacote.

O codigo de verdade fica em src/clipador/. Depois de `pip install -e .` da pra usar
so `clipador "<link>"`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from clipador.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
