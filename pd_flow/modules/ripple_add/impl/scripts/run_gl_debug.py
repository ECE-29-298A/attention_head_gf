#!/usr/bin/env python3
"""Copy of test/top/run.py's flow (unchanged test module) with waves on and a kept build dir,
used only to locate the first X in the gate-level top simulation. Usage:
run_gl_debug.py NETLIST CELL_MODELS BUILD_DIR [TESTCASE]"""
import os, sys
from pathlib import Path
from cocotb_tools.runner import get_runner
ROOT = Path(__file__).resolve().parents[5]
net, models, build = (Path(a).resolve() for a in sys.argv[1:4])
tc = sys.argv[4] if len(sys.argv) > 4 else "end_to_end_flash_and_host"
r = get_runner("icarus")
_tc = r._test_command
def _vcd():
    cmds = _tc()
    return [[("-vcd" if a == "-fst" else a) for a in c] + ["+dumpfile_path=" + str(build / "dump.vcd")] for c in cmds]
r._test_command = _vcd
r.build(sources=[models, net], hdl_toplevel="tt_um_attention_head_gf", build_dir=build, always=True,
        timescale=("1ns", "1ps"), build_args=["-g2012"], waves=True)
r.test(test_module="test_top_qspi", hdl_toplevel="tt_um_attention_head_gf", build_dir=build,
       test_dir=build, waves=True, testcase=tc,
       extra_env={"PYTHONPATH": os.pathsep.join([str(ROOT / "test/top"), str(ROOT / "python/src")]),
                  "OUTPUTS": "8"})
