"""Run both SPI byte wrappers with the shared Verilog testbench."""

from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
TEST = Path(__file__).resolve().parent / "tb_spi_byte.v"
RTL = [
    ROOT / "src/spi_multi_io_byte.v",
    ROOT / "src/qspi_byte.v",
    ROOT / "src/ospi_byte.v",
]


with TemporaryDirectory(prefix="spi-byte-verilog-") as temporary:
    for lanes, name in ((4, "qspi"), (8, "ospi")):
        binary = Path(temporary) / name
        run(["iverilog", "-g2005", "-s", "tb_spi_byte",
             f"-Ptb_spi_byte.LANES={lanes}", "-o", str(binary),
             *(str(source) for source in RTL), str(TEST)], check=True)
        run(["vvp", str(binary)], check=True)
