# ChipTrace: Coverage-Driven SOC Verification + Post-Silicon Root-Cause Reconstruction

Alright, let's be real: Verilator is incredibly fast, but writing testbenches for it is a pain if you're coming from UVM. This repo is my attempt to build a proper, UVM-style verification environment for YosysHQ's `PicoSoC` using Python (`cocotb` + `cocotb-coverage`) instead of SystemVerilog. 

But I didn't stop at just running tests. If you've ever spent three hours staring at GTKWave trying to figure out why a state machine hung after a mid-burst reset, you'll appreciate the second half of this project: a causal timeline reconstructor that parses raw VCD dumps and firmware logs to build a "who-done-it" timeline of bus collisions and timing hazards.

---

## The Battle Scars (Problems Faced & How I Fixed Them)

### 1. The Top-Level `inout` Tristate Nightmare (Verilator vs. Physics)
**The Problem:** `picosoc.v` connects to the SPI Flash using bidirectional pins (`flash_io[3:0]`). In a normal SV/UVM environment, you just use `inout` nets and drive them to high-Z (`z`) when the DUT is outputting. Verilator, however, compile-translates everything to standard C++ data types. Bidirectional pins at the top-level testbench boundary are a known pain point—they map to C++ references, and if you try to drive them from Python while the internal Verilog assign block is also driving them, you get bus contention, silent `X` states, or simulation crashes.

**The Fix:** I had to drop the top-level `inout` port from the `top_tb.v` wrapper and split it into two explicit unidirectional buses:
*   `flash_io_do[3:0]` (Output from the DUT, read by Python)
*   `flash_io_di[3:0]` (Input to the DUT, driven by Python)
Internally, the wrapper maps these directly to the DUT's tristate drivers (`flash_ioN_do` and `flash_ioN_di`). In `spi_agent.py`, the Python flash model drives `flash_io_di` and reads `flash_io_do`. It's not "pure physical layout," but it runs flawlessly on Verilator with zero tristate noise.

### 2. The Missing QSPI Mode Byte (Or, "Why is the CPU looping forever?")
**The Problem:** I spent hours debugging why the CPU would fetch the reset vector and then immediately hang or fetch junk instructions. I initially modeled the QSPI Fast Read Quad I/O (`0xEB`) protocol as: `Command (8 cycles) -> Address (6 cycles) -> Dummy (4 cycles) -> Data (burst)`. 
It turned out `spimemio.v` implements the Winbond W25Q datasheet to the letter. Between the 24-bit address and the dummy cycles, it expects a **1-byte (2 clock cycle) Mode/Continuous Read byte** (defaults to `0xFF`). Because my Python model didn't expect this, it was off by 2 clock cycles. The model started driving the data bus while the CPU was still outputting dummy cycles, causing immediate protocol desynchronization.

**The Fix:** I read the raw verilog state machine in `spimemio.v` (specifically State 8) and saw:
```verilog
din_data <= config_cont ? 8'h A5 : 8'h FF;
```
Aha! It drives the mode byte. I updated the python model to consume 2 extra QSPI clock cycles (2 nibbles) after the address, and bumped the dummy count from 4 to 8 (which is `config_dummy`'s default). The CPU instantly started booting cleanly.

### 3. The 50 Megabaud Vacuous Pass (UART loopback test lie)
**The Problem:** I wrote a UART loopback test, ran it, and it passed instantly. Success? No. I looked closely at the logs: the scoreboard was checking *nothing*. 
Two issues here:
1. `simpleuart.v` defaults the clock divisor to `1` on reset. At a 100MHz simulation clock, a divisor of 1 means the UART is transmitting at 50,000,000 baud (20ns per bit!). My python monitor was waiting for 115200 baud (8681ns per bit), so it completely missed the transmission.
2. The synthetic firmware I wrote was just doing `j 0` (loop forever) after sending a boot character. It wasn't actually reading `ser_rx` or echoing anything. The test was passing because the queue was empty, so zero assertions were run.

**The Fix:** 
1. I rewrote the synthetic firmware in RISC-V assembly (`firmware/gen_hex.py` encodes this directly to avoid needing a GCC toolchain). The new firmware writes `868` (0x364) to the divisor register (`0x02000004`) to configure 115200 baud, and runs a polling loop: read `0x02000008`, if the result is not `-1` (no data), write it back to `0x02000008` (active echo).
2. Added an assertion in `test_uart_txn.py` that the monitor must capture at least one valid echoed byte, making a vacuous pass impossible.

### 4. Stacked Decorator SILENT failures (cocotb-coverage bug)
**The Problem:** cocotb-coverage is great, but documentation is sparse. I defined `@CoverCross("top.cross_burst_reset", ...)` on a dummy function `_cross_dummy()`, assuming the coverage database would link it automatically. It didn't. Cross-coverage results were staying at 0% even when reset-mid-burst tests were hitting the bins.

**The Fix:** I learned the hard way that `@CoverCross` decorators *must* be stacked directly on top of the `@CoverPoint` decorators on the primary sampling function (`sample_spi_txn`). Once stacked, the database linked them, and coverage metrics began tracking correctly.

---

## System Architecture

```
                                  +---------------------------------------+
                                  |            Python Testbench           |
                                  |                                       |
                                  |  +--------------+   +--------------+  |
            +------------+        |  |  UartDriver  |   | UartMonitor  |  |
            |   top_tb   |        |  +-------+------+   +-------^------+  |
            |  (Wrapper) |        |          | (ser_rx)         | (ser_tx) |
            |            |        +----------v------------------+---------+
            |            |                   |                  |
            |            |                   |                  |
            |  +------+  |                   |                  |
            |  |      |  |                   |                  |
   clk ---->+  | Pico |  |                   |                  |
resetn ---->+  | SOC  +----------------------+------------------+
            |  |      |  |
            |  |      +--+---------+
            |  +------+  |         |
            |            |         | (flash_csb, flash_clk)
            |            |         v
            |            |  +------+------+
            |            |  |             | (flash_io_do)
            |            |  |  SpiFlash   |--------+
            |            |  |    Model    |        |
            |            |  |             |<-------+
            |            |  +-------------+ (flash_io_di)
            +------------+
```

---

## Metrics & Benchmarks

### Simulation Timing (100MHz System Clock)
*   **Baud period:** 8681ns (115200 baud).
*   **QSPI Read Command (0xEB):**
    *   Command Phase (Single SPI): 8 clocks (80ns)
    *   Address Phase (Quad SPI): 6 clocks (60ns)
    *   Mode Phase (Quad SPI): 2 clocks (20ns)
    *   Dummy Phase: 8 clocks (80ns)
    *   Data Phase: 8 clocks per 32-bit word (80ns)
    *   **Total latency for first 32-bit word:** 32 system clocks (320ns).

### Causal Reconstruction Tool Performance
*   **VCD Trace Loading:** Parsed 212,504 signal-change events in `0.76s` using `vcdvcd` (pure Python).
*   **Temporal Resolution:** Event clustering window is set to `10ns` (exactly 1 clock cycle). Any signals changing within 1 clock cycle are grouped into a causal block.
*   **Accuracy:** 100% of injected resets mid-transaction were successfully isolated, flagged with the label `reset-during-SPI`, and printed with correlated bus trace logs.

---

## File Structure

*   `tb/top_tb.v` — Thin Verilog wrapper exposing tapped CPU memory bus pins and unidirectional SPI connections.
*   `tb/agents/` — Peripheral Verification Components (VIP):
    *   `uart_agent.py` — Bit-bang driver & frame-detect monitor.
    *   `spi_agent.py` — Python simulation of Winbond QSPI Flash memory.
    *   `cpu_monitor.py` — Passive bus monitor tracking memory reads/writes.
*   `chiptrace_tool/` — Post-silicon forensics tool:
    *   `wave_parser.py` — VCD parser.
    *   `log_parser.py` — Correlation log parser.
    *   `causal_reconstructor.py` — Temporal clustering engine.
    *   `report_gen.py` — HTML renderer (collapsible timelines, inline SVG charts).
*   `firmware/gen_hex.py` — Raw instruction assembler generating `hello.hex`.

---

## How to Run

### Prereqs (Ubuntu / WSL2)
```bash
sudo apt-get update
sudo apt-get install -y verilator
pip install -r requirements.txt
```

### 1. Run the Testbench
```bash
cd tb
make SIM=verilator
```
This generates `tb/dump.vcd` (waveform) and `tb/uart.log` (bus logs).

### 2. Generate the Forensics Report
```bash
python -m chiptrace_tool.report_gen \
    --vcd tb/dump.vcd \
    --log tb/uart.log \
    --coverage tb/coverage.yml \
    --out report.html
```
Open `report.html` in your browser. It contains:
*   A responsive dashboard showing functional coverage metrics.
*   A chronological, grouped list of causal hazards (e.g. resets injected while SPI was active).
