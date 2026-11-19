"""Run the QSPI Tiny Tapeout top integration test in a temporary directory."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = [
    "src/project.v", "src/attention_controller.sv", "src/score_mac.v",
    "src/ripple_add.v", "src/max_reg.v", "src/accum.v",
    "src/exp_lut.v", "src/divider.v",
    "src/Memaccess/qspi_read_adapter.v", "src/Memaccess/qspi_byte.v",
    "src/Memaccess/spi_multi_io_byte.v",
]


def main():
    with tempfile.TemporaryDirectory(prefix="attention-top-") as directory:
        build = Path(directory)
        runner = get_runner("icarus")
        runner.build(sources=[ROOT / name for name in SOURCES],
                     hdl_toplevel="tt_um_attention_head_gf", build_dir=build,
                     always=True, timescale=("1ns", "1ps"),
                     build_args=["-g2012"])
        runner.test(test_module="test_top_qspi", hdl_toplevel="tt_um_attention_head_gf",
                    build_dir=build, test_dir=build,
                    extra_env={"PYTHONPATH": os.pathsep.join([str(HERE), str(ROOT / "python/src")])})
        subprocess.run([sys.executable, "-m", "cocotb_tools.check_results",
                        str(build / "results.xml")], check=True)


if __name__ == "__main__":
    main()
