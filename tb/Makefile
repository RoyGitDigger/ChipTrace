SIM              ?= verilator
TOPLEVEL_LANG    ?= verilog

COCOTB_HDL_TIMEUNIT      = 1ns
COCOTB_HDL_TIMEPRECISION = 1ps

DUT_DIR := $(abspath ../dut/picorv32)

VERILOG_SOURCES += $(DUT_DIR)/picosoc/picosoc.v
VERILOG_SOURCES += $(DUT_DIR)/picosoc/spimemio.v
VERILOG_SOURCES += $(DUT_DIR)/picosoc/simpleuart.v
VERILOG_SOURCES += $(DUT_DIR)/picorv32.v
VERILOG_SOURCES += $(abspath top_tb.v)

TOPLEVEL = top_tb

MODULE = test_boot,test_uart_txn,test_spi_burst,test_reset_midburst

ifeq ($(SIM), verilator)
  EXTRA_ARGS += --trace --trace-structs --trace-depth 5 -Wno-fatal
  EXTRA_ARGS += -CFLAGS "-std=c++14"
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
