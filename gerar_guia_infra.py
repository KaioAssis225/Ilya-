"""Compatibilidade: gera o guia v2 usando o gerador mantido em ops/."""

from runpy import run_path
from pathlib import Path


run_path(
    str(Path(__file__).resolve().parent / "ops" / "generate_infra_guide.py"),
    run_name="__main__",
)
