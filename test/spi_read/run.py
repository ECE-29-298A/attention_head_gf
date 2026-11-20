"""Check spi_read against a behavioural flash, from several random power-up states."""
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test"))
from rtl_sim import build, simulate


def main():
    with tempfile.TemporaryDirectory(prefix="attention-spi-read-") as directory:
        binary = build(Path(directory), "tb_spi_read",
                       ["test/spi_read/tb_spi_read.sv", "test/spi_flash_model.sv", "src/spi_read.v"],
                       "--x-initial", "unique")
        for seed in (298, 2026, 16):
            simulate(binary, "+verilator+rand+reset+2", f"+verilator+seed+{seed}")


if __name__ == "__main__":
    main()
