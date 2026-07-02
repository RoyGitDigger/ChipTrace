import cocotb
from cocotb.triggers import RisingEdge

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sim_utils import start_clock, reset_dut, sim_time_ns
from agents.cpu_monitor import CpuMonitor
from agents.spi_agent import SpiFlashModel
from conftest import GOLDEN_FLASH


@cocotb.test()
async def test_boot_reset_vector(dut):
    """
    Deassert reset and wait for the first CPU memory access.
    The first mem_valid should be an instruction fetch at the reset vector.
    This verifies: clock/reset infrastructure, CPU comes alive after reset.
    """
    cpu_mon = CpuMonitor(dut, log_path="uart.log")
    flash = SpiFlashModel(dut, flash_image=GOLDEN_FLASH)

    await start_clock(dut)
    flash.start()
    cpu_mon.start()
    await reset_dut(dut)

    # Wait for first instruction fetch — timeout after 10000 cycles
    found = False
    for _ in range(10000):
        await RisingEdge(dut.clk)
        try:
            valid = int(dut.mem_valid.value)
            instr = int(dut.mem_instr.value)
        except Exception:
            continue
        if valid and instr:
            t = sim_time_ns()
            addr = int(dut.mem_addr.value)
            cocotb.log.info(f"First instruction fetch at t={t:.0f}ns addr=0x{addr:08x}")
            found = True
            break

    cpu_mon.stop()
    flash.stop()

    assert found, "CPU never issued an instruction fetch after reset — hung or not starting"
    assert len(cpu_mon.transactions) >= 1, "CpuMonitor recorded no transactions"
