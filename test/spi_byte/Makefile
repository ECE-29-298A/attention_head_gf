.PHONY: test test-cocotb test-verilog lint

RTL = ../../src/Memaccess/spi_multi_io_byte.v ../../src/Memaccess/qspi_byte.v ../../src/Memaccess/ospi_byte.v

test: test-cocotb test-verilog

test-verilog:
	python3 -B run_verilog.py

test-cocotb:
	PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q test_cocotb_runner.py

lint:
	verilator --lint-only -Wall --top-module qspi_byte $(RTL)
	verilator --lint-only -Wall --top-module ospi_byte $(RTL)
