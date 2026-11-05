"""Small Verilator helper shared by the divider and controller regressions."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(work, top, sources, *options):
    verilator = shutil.which("verilator")
    if not verilator:
        raise SystemExit("Verilator is required.")
    command = [verilator, "--binary", "--timing", "--assert", "-Wno-fatal",
               "--top-module", top, "--Mdir", str(work / "obj"), *options]
    command += [str(ROOT / source) for source in sources]
    result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    for line in result.stderr.splitlines():
        if line.startswith("%Warning"):
            print(line, flush=True)
    return work / "obj" / f"V{top}"


def simulate(binary, *options):
    result = subprocess.run([str(binary), *options], cwd=binary.parent,
                            capture_output=True, text=True, timeout=90)
    print(result.stdout, end="", flush=True)
    if result.returncode:
        raise SystemExit(result.stderr or f"Simulation exited with {result.returncode}")
