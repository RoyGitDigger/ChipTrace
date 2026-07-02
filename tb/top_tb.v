// Thin Verilog wrapper around picosoc for the cocotb testbench.
//
// picosoc.v exposes individual OE/DO/DI signals for each SPI IO pin
// rather than a single inout bus. This wrapper implements the tristate
// mux so the testbench sees a clean inout flash_io[3:0] bus, and so
// the SPI flash model in the Python agent can drive/sample a single
// 4-bit wire without caring about the OE logic inside the DUT.
//
// Everything else is a straight pass-through. No logic added.

`timescale 1ns/1ps

module top_tb (
    input  wire       clk,
    input  wire       resetn,

    // SPI flash — exposed as inout to the testbench
    output wire       flash_csb,
    output wire       flash_clk,
    inout  wire [3:0] flash_io,

    // UART
    output wire       ser_tx,
    input  wire       ser_rx,

    // Memory bus — exposed so cpu_monitor can snoop without internal probing
    output wire        mem_valid,
    output wire        mem_instr,
    input  wire        mem_ready,
    output wire [31:0] mem_addr,
    output wire [31:0] mem_wdata,
    output wire [ 3:0] mem_wstrb,
    input  wire [31:0] mem_rdata,

    // IO peripheral bus — for GPIO / user peripheral tests
    output wire        iomem_valid,
    input  wire        iomem_ready,
    output wire [ 3:0] iomem_wstrb,
    output wire [31:0] iomem_addr,
    output wire [31:0] iomem_wdata,
    input  wire [31:0] iomem_rdata
);

    // Tristate mux: per-pin OE/DO from DUT, DI back into DUT
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

        .iomem_valid  (iomem_valid),
        .iomem_ready  (iomem_ready),
        .iomem_wstrb  (iomem_wstrb),
        .iomem_addr   (iomem_addr),
        .iomem_wdata  (iomem_wdata),
        .iomem_rdata  (iomem_rdata)
    );

    // CPU bus monitor probe wires — tap into the picorv32 instance inside picosoc.
    // Wire names match picorv32's native memory interface.
    assign mem_valid = dut.cpu.mem_valid;
    assign mem_instr = dut.cpu.mem_instr;
    assign mem_addr  = dut.cpu.mem_addr;
    assign mem_wdata = dut.cpu.mem_wdata;
    assign mem_wstrb = dut.cpu.mem_wstrb;

    // mem_ready and mem_rdata are driven back into cpu from soc interconnect
    assign mem_ready = dut.mem_ready;
    assign mem_rdata = dut.mem_rdata;

endmodule
