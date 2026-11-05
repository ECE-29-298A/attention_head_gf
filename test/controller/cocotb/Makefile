SIM ?= icarus
TOPLEVEL_LANG = verilog
ROOT := $(CURDIR)/source
VERILOG_SOURCES = $(ROOT)/src/attention_controller.sv $(ROOT)/src/score_mac.v $(ROOT)/src/max_reg.v $(ROOT)/src/accum.v $(ROOT)/src/exp_lut.v $(ROOT)/src/divider.v
TOPLEVEL = attention_controller
COCOTB_TEST_MODULES = test_attention_controller
COMPILE_ARGS += -g2012
include $(shell cocotb-config --makefiles)/Makefile.sim
