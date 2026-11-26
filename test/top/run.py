"""Run the QSPI Tiny Tapeout top integration test in a temporary directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = [
    "src/project.v", "src/attention_controller.sv", "src/mac_unit.v",
    "src/ripple_add.v", "src/max_reg.v",
    "src/exp_lut.v", "src/divider.v",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=Path, help="Mapped or routed top to simulate")
    parser.add_argument("--cell-models", type=Path, help="Verilog models for netlist cells")
    parser.add_argument("--outputs", type=int, choices=(2, 4, 8), default=8,
                        help="the top's OUTPUTS parameter (RTL only; a netlist is built with 8)")
    args = parser.parse_args()
    if bool(args.netlist) != bool(args.cell_models):
        parser.error("--netlist and --cell-models must be supplied together")
    sources = ([args.cell_models.resolve(strict=True), args.netlist.resolve(strict=True)]
               if args.netlist else [ROOT / name for name in SOURCES])
    with tempfile.TemporaryDirectory(prefix="attention-top-") as directory:
        build = Path(directory)
        runner = get_runner("icarus")
        runner.build(sources=sources,
                     hdl_toplevel="tt_um_attention_head_gf", build_dir=build,
                     always=True, timescale=("1ns", "1ps"),
                     build_args=["-g2012"],
                     parameters={} if args.netlist else {"OUTPUTS": args.outputs})
        runner.test(test_module="test_top_qspi", hdl_toplevel="tt_um_attention_head_gf",
                    build_dir=build, test_dir=build,
                    extra_env={"PYTHONPATH": os.pathsep.join([str(HERE), str(ROOT / "python/src")]),
                               "OUTPUTS": str(8 if args.netlist else args.outputs)})
        subprocess.run([sys.executable, "-m", "cocotb_tools.check_results",
                        str(build / "results.xml")], check=True)


if __name__ == "__main__":
    main()
