"""Pin-level top check under Verilator: Python-model vectors, behavioural flash,
random host timing, aborts and power-up state."""
import importlib.util
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test"))
from rtl_sim import build, simulate

# The controller regression already builds the directed and random cases.
spec = importlib.util.spec_from_file_location("controller_run", ROOT / "test/controller/run.py")
controller_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller_run)


def main():
    sources = ["test/top/tb_top.sv", "test/spi_flash_model.sv", "src/project.v",
               "src/attention_controller.sv", "src/score_mac.v", "src/ripple_add.v",
               "src/max_reg.v", "src/accum.v", "src/exp_lut.v", "src/divider.v", "src/spi_read.v"]
    with tempfile.TemporaryDirectory(prefix="attention-top-pins-") as directory:
        work = Path(directory)
        lines = list(controller_run.vectors())
        (work / "vectors.txt").write_text("\n".join(lines) + "\n")
        binary = build(work, "tb_top", sources, "--x-initial", "unique")
        for seed in (298, 2026, 16):
            simulate(binary, f"+VECTORS={work / 'vectors.txt'}", f"+CASES={len(lines)}",
                     "+verilator+rand+reset+2", f"+verilator+seed+{seed}")


if __name__ == "__main__":
    main()
