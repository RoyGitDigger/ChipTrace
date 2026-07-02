// Thin Verilog wrapper around picosoc for the cocotb testbench.
//
// picosoc.v exposes individual OE/DO/DI signals for each SPI IO pin
// rather than a single inout bus. This wrapper implements the tristate
// mux so the testbench sees a clean inout flash_io[3:0] bus, and so
// the SPI flash model in the Python agent can drive/sample a single
// 4-bit wire without caring about the OE logic inside the DUT.
//
// mem_valid / mem_ready / mem_addr / mem_wdata / mem_wstrb / mem_rdata
// are module-level wires in picosoc.v (not buried inside cpu). We just
// re-export them as top-level ports so the cocotb cpu_monitor can bind.

`timescale 1ns/1ps

module top_tb (
    input  wire       clk,
    input  wire       resetn,

    // SPI flash — exposed as inout for the Python SPI flash model
    output wire       flash_csb,
    output wire       flash_clk,
    inout  wire [3:0] flash_io,

    // UART
    output wire       ser_tx,
    input  wire       ser_rx,

    // CPU bus — re-exported from picosoc's module-level wires
    output wire        mem_valid,
    output wire        mem_instr,
    output wire        mem_ready,
    output wire [31:0] mem_addr,
    output wire [31:0] mem_wdata,
    output wire [ 3:0] mem_wstrb,
    output wire [31:0] mem_rdata,

    // IO peripheral bus
    output wire        iomem_valid,
    input  wire        iomem_ready,
    output wire [ 3:0] iomem_wstrb,
    output wire [31:0] iomem_addr,
    output wire [31:0] iomem_wdata,
    input  wire [31:0] iomem_rdata
);

    // Tristate mux: per-pin OE/DO from DUT, DI feeds back in
    wire flash_io0_oe, flash_io1_oe, flash_io2_oe, flash_io3_oe;
    wire flash_io0_do, flash_io1_do, flash_io2_do, flash_io3_do;
    wire flash_io0_di, flash_io1_di, flash_io2_di, flash_io3_di;

    assign flash_io[0] = flash_io0_oe ? flash_io0_do : 1'bz;
    assign flash_io[1] = flash_io1_oe ? flash_io1_do : 1'bz;
    assign flash_io[2] = flash_io2_oe ? flash_io2_do : 1'bz;
    assign flash_io[3] = flash_io3_oe ? flash_io3_do : 1'bz;

    assign flash_io0_di = flash_io[0];
    assign flash_io1_di = flash_io[1];
    assign flash_io2_di = flash_io[2];
    assign flash_io3_di = flash_io[3];

    // Internal wires to tap picosoc's mem bus
    wire _mem_valid, _mem_instr, _mem_ready;
    wire [31:0] _mem_addr, _mem_wdata, _mem_rdata;
    wire [ 3:0] _mem_wstrb;

    picosoc #(
        .MEM_WORDS(256)
    ) dut (
        .clk          (clk),
        .resetn       (resetn),

        .flash_csb    (flash_csb),
        .flash_clk    (flash_clk),
        .flash_io0_oe (flash_io0_oe),
        .flash_io1_oe (flash_io1_oe),
        .flash_io2_oe (flash_io2_oe),
        .flash_io3_oe (flash_io3_oe),
        .flash_io0_do (flash_io0_do),
        .flash_io1_do (flash_io1_do),
        .flash_io2_do (flash_io2_do),
        .flash_io3_do (flash_io3_do),
        .flash_io0_di (flash_io0_di),
        .flash_io1_di (flash_io1_di),
        .flash_io2_di (flash_io2_di),
        .flash_io3_di (flash_io3_di),

        .ser_tx       (ser_tx),
        .ser_rx       (ser_rx),

        .irq_5        (1'b0),
        .irq_6        (1'b0),
        .irq_7        (1'b0),

        .iomem_valid  (iomem_valid),
        .iomem_ready  (iomem_ready),
        .iomem_wstrb  (iomem_wstrb),
        .iomem_addr   (iomem_addr),
        .iomem_wdata  (iomem_wdata),
        .iomem_rdata  (iomem_rdata)
    );

    // Tap picosoc's internal mem bus wires (they're at module scope in picosoc.v)
    assign mem_valid = dut.mem_valid;
    assign mem_instr = dut.mem_instr;
    assign mem_ready = dut.mem_ready;
    assign mem_addr  = dut.mem_addr;
    assign mem_wdata = dut.mem_wdata;
    assign mem_wstrb = dut.mem_wstrb;
    assign mem_rdata = dut.mem_rdata;

endmodule
