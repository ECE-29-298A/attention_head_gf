# Block-level tests: one Verilog module at a time, no tb.v wrapper.
# Usage:  make mac_unit
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = ../../src
COCOTB_HDL_TIMEUNIT = 1ns
COCOTB_HDL_TIMEPRECISION = 1ps

VERILOG_SOURCES = $(SRC_DIR)/$(MODULE_UNDER_TEST).v $(SRC_DIR)/ripple_add.v
TOPLEVEL = $(MODULE_UNDER_TEST)
COCOTB_TEST_MODULES = test_$(MODULE_UNDER_TEST)
SIM_BUILD = sim_build/$(MODULE_UNDER_TEST)

include $(shell cocotb-config --makefiles)/Makefile.sim

mac_unit max_reg exp_lut:
	$(MAKE) MODULE_UNDER_TEST=$@ sim
