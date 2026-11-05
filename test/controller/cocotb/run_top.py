"""Run the configured Tiny Tapeout top's Cocotb test in a temporary build directory."""
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix="attention-top-cocotb-") as build:
        Path(build, "Makefile").write_text((HERE / "Makefile.top").read_text())
        Path(build, "source").symlink_to(HERE.parents[2], target_is_directory=True)
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(HERE.parents[2] / "test"), env.get("PYTHONPATH", "")]))
        subprocess.run(["make", "-f", str(Path(build) / "Makefile")], cwd=build, env=env, check=True)
        subprocess.run(["python3", "-m", "cocotb_tools.check_results", str(Path(build) / "results.xml")], cwd=build, env=env, check=True)


if __name__ == "__main__":
    main()
