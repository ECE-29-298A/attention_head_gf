"""Build and run the same cocotb checks against both public top modules."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cocotb_tools.runner import get_runner


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


@pytest.mark.parametrize("top", ["qspi_byte", "ospi_byte"])
def test_spi_byte(top):
    with TemporaryDirectory(prefix=f"{top}-") as temporary:
        build_dir = Path(temporary)
        runner = get_runner("icarus")
        runner.build(
            sources=[
                ROOT / "src" / "spi_multi_io_byte.v",
                ROOT / "src" / "qspi_byte.v",
                ROOT / "src" / "ospi_byte.v",
            ],
            hdl_toplevel=top,
            build_dir=build_dir,
            always=True,
            timescale=("1ns", "1ps"),
        )
        runner.test(
            test_module="cocotb_spi_byte",
            hdl_toplevel=top,
            build_dir=build_dir,
            test_dir=build_dir,
            extra_env={"PYTHONPATH": str(HERE)},
        )
