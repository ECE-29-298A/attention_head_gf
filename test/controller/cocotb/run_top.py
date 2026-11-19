"""Compatibility entry point for the integrated Tiny Tapeout top test."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
subprocess.run([sys.executable, str(ROOT / "test/top/run.py")], check=True)
