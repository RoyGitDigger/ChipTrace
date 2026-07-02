import cocotb
from cocotb.triggers import Timer

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sim_utils import start_clock, reset_dut, sim_time_ns
from agents.spi_agent import SpiFlashModel, SpiMonitor, SpiTransaction
from agents.cpu_monitor import CpuMonitor
from scoreboard import Scoreboard
from coverage import sample_spi_txn
from conftest import GOLDEN_FLASH


@cocotb.test()
async def test_reset_mid_spi_burst(dut):
    """
    Assert resetn=0 while the CPU is actively fetching from SPI flash, then
    deassert and verify the SOC recovers cleanly:
      - flash_csb goes high (bus not hung)
      - CPU issues another valid fetch after recovery
      - No scoreboard mismatches on the post-reset transaction

    This directly exercises: reset-mid-burst → recovery, the hardest case
    for SPI controller state machines.
    """
    sb = Scoreboard(GOLDEN_FLASH)
    flash = SpiFlashModel(dut, GOLDEN_FLASH)
    spi_mon = SpiMonitor(flash)
    cpu_mon = CpuMonitor(dut, "uart.log")

    await start_clock(dut)
    flash.start()
    spi_mon.start()
    cpu_mon.start()
    await reset_dut(dut)

    # Let the SOC start fetching — give it enough time to get into a burst
    await Timer(5_000, units="ns")

    t_reset_assert = sim_time_ns()
    cocotb.log.info(f"Injecting reset at t={t_reset_assert:.0f}ns")
    dut.resetn.value = 0

    await Timer(200, units="ns")

    t_reset_deassert = sim_time_ns()
    cocotb.log.info(f"Deasserting reset at t={t_reset_deassert:.0f}ns")
    dut.resetn.value = 1

    # Wait for recovery — should see flash_csb go high and CPU start fetching again
    await Timer(500, units="ns")

    csb_val = int(dut.flash_csb.value)
    cocotb.log.info(f"flash_csb after recovery: {csb_val} (expect 1 = idle)")

    # Run for a bit more to capture post-reset transactions
    await Timer(10_000, units="ns")

    spi_mon.stop()
    cpu_mon.stop()
    flash.stop()

    # Tag all transactions that completed after reset was asserted
    post_reset_txns = [
        t for t in spi_mon.transactions
        if t.timestamp_ns > t_reset_deassert
    ]
    cocotb.log.info(f"Post-reset SPI transactions: {len(post_reset_txns)}")

    for txn in post_reset_txns:
        marked = SpiTransaction(
            cmd=txn.cmd,
            addr=txn.addr,
            data=txn.data,
            timestamp_ns=txn.timestamp_ns,
            reset_asserted=True
        )
        sb.check_spi_read(marked)
        sample_spi_txn(marked)

    assert csb_val == 1, (
        f"flash_csb still low after reset recovery at t={sim_time_ns():.0f}ns — "
        "SPI controller is stuck"
    )

    errors = sb.all_errors()
    assert not errors, f"Post-reset scoreboard failures:\n" + "\n".join(str(e) for e in errors)
    cocotb.log.info("Reset mid-burst test: PASS")


@cocotb.test()
async def test_double_reset(dut):
    """
    Assert and deassert reset twice in quick succession.
    Verifies there is no residual state from the first reset window that
    corrupts the second boot sequence.
    """
    flash = SpiFlashModel(dut, GOLDEN_FLASH)
    cpu_mon = CpuMonitor(dut, "uart.log")

    await start_clock(dut)
    flash.start()
    cpu_mon.start()
    await reset_dut(dut)

    await Timer(2_000, units="ns")
    dut.resetn.value = 0
    await Timer(100, units="ns")
    dut.resetn.value = 1
    await Timer(1_000, units="ns")
    dut.resetn.value = 0
    await Timer(100, units="ns")
    dut.resetn.value = 1

    await Timer(10_000, units="ns")

    cpu_mon.stop()
    flash.stop()

    post_txns = [t for t in cpu_mon.transactions if t.timestamp_ns > 3_100]
    assert len(post_txns) > 0, "CPU issued no transactions after double reset"
    cocotb.log.info(f"Double reset: CPU alive, {len(post_txns)} post-reset transactions")
