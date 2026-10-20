# Block-level tests: one Verilog module at a time, no tb.v wrapper.
# Usage:  make score_mac
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../../src
COCOTB_HDL_TIMEUNIT = 1ns
COCOTB_HDL_TIMEPRECISION = 1ps

VERILOG_SOURCES = $(SRC_DIR)/$(MODULE_UNDER_TEST).v
TOPLEVEL = $(MODULE_UNDER_TEST)
COCOTB_TEST_MODULES = test_$(MODULE_UNDER_TEST)
SIM_BUILD = sim_build/$(MODULE_UNDER_TEST)

include $(shell cocotb-config --makefiles)/Makefile.sim

score_mac max_reg accum:
	$(MAKE) MODULE_UNDER_TEST=$@ sim