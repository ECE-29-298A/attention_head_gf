# Block-level tests: one Verilog module at a time, no tb.v wrapper.
# Usage:  make mac_unit   (OUTPUTS=4 make mac_unit for another ring depth; default 8)
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = ../../src
COCOTB_HDL_TIMEUNIT = 1ns
COCOTB_HDL_TIMEPRECISION = 1ps

VERILOG_SOURCES = $(SRC_DIR)/$(MODULE_UNDER_TEST).v $(SRC_DIR)/ripple_add.v
TOPLEVEL = $(MODULE_UNDER_TEST)
COCOTB_TEST_MODULES = test_$(MODULE_UNDER_TEST)
SIM_BUILD = sim_build/$(MODULE_UNDER_TEST)
ifeq ($(MODULE_UNDER_TEST),mac_unit)
OUTPUTS ?= 8
export OUTPUTS
COMPILE_ARGS += -Pmac_unit.OUTPUTS=$(OUTPUTS)
SIM_BUILD := $(SIM_BUILD)_$(OUTPUTS)
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

mac_unit max_reg exp_lut:
	$(MAKE) MODULE_UNDER_TEST=$@ sim
