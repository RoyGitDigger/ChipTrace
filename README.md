# ChipTrace

Coverage-driven SOC verification environment for PicoSoC, plus an automated
post-silicon-style debug tool that reconstructs causal failure timelines from
waveform dumps and firmware logs.

## What's in here

```
chiptrace/
├── dut/picorv32/       git submodule — YosysHQ/picorv32 (the DUT)
├── tb/                 cocotb testbench
│   ├── agents/         UVM-style driver/monitor agents per peripheral
│   ├── scoreboard.py   golden reference model + comparison logic
│   ├── coverage.py     functional coverage: CoverPoints + CoverCross
│   └── test_*.py       four test suites (boot, UART, SPI burst, reset mid-burst)
├── chiptrace_tool/     post-failure causal reconstruction tool
│   ├── wave_parser.py      loads VCD signal events
│   ├── log_parser.py       parses timestamped firmware UART logs
│   ├── causal_reconstructor.py  clusters events, flags races/interactions
│   └── report_gen.py       renders self-contained HTML timeline + coverage dashboard
├── firmware/hello.hex  synthetic PicoRV32 firmware image used by tests
└── .github/workflows/  CI: Verilator + cocotb on every push, HTML report artifact
```

## DUT: PicoSoC

PicoSoC from YosysHQ/picorv32 — real SOC with PicoRV32 CPU, SPI flash
controller, memory-mapped UART, and GPIO. Memory map:

| Range | Description |
|---|---|
| `0x00000000–0x00FFFFFF` | Internal SRAM |
| `0x01000000–0x01FFFFFF` | SPI flash (XIP) |
| `0x02000004` | UART clock divider |
| `0x02000008` | UART data register |
| `0x03000000+` | User peripherals / GPIO |

## Setup (Ubuntu 22.04 / WSL2)

```bash
sudo apt install verilator gtkwave
git clone --recurse-submodules https://github.com/yourname/chiptrace.git
cd chiptrace
pip install -r requirements.txt
```

## Running the testbench

```bash
cd tb
make SIM=verilator
```

VCD waveform is written to `tb/dump.vcd`. Pass `WAVES=1` to enable tracing
even when tests pass.

## Running the causal reconstruction tool

After a failing run:

```bash
python -m chiptrace_tool.report_gen \
    --vcd tb/dump.vcd \
    --log tb/uart.log \
    --coverage tb/coverage.yml \
    --out report.html
```

Open `report.html` in any browser. No server needed.

## Coverage model

Four CoverPoints tracked per run:

- `spi_burst_len` — bins: 1, 2, 4, 8, 16, 32 bytes
- `reset_during_txn` — True / False
- `uart_byte_class` — control / printable / high
- Cross: `burst_len × reset_mid_txn`

## CI

GitHub Actions runs Verilator + cocotb on every push. The HTML coverage report
is uploaded as a workflow artifact after each run.

## Tool stack

| Purpose | Tool |
|---|---|
| RTL simulator | Verilator 5.x |
| Verification framework | cocotb 1.9.x |
| Coverage | cocotb-coverage |
| Waveform parsing | vcdvcd |
| DUT | PicoSoC (YosysHQ/picorv32) |
| CI | GitHub Actions |
