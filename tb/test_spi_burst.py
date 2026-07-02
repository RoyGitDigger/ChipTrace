import cocotb
from cocotb.triggers import RisingEdge, Timer

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sim_utils import start_clock, reset_dut, wait_n_cycles, sim_time_ns
from agents.spi_agent import SpiFlashModel, SpiMonitor, SpiTransaction
from agents.cpu_monitor import CpuMonitor
from scoreboard import Scoreboard
from coverage import sample_spi_txn


GOLDEN_FLASH = bytes([
    0x6F, 0x00, 0x00, 0x00,
    *range(4, 256)
])


@cocotb.test()
async def test_spi_burst_read(dut):
    """
    Let the CPU boot and fetch from SPI flash.  The SpiFlashModel responds to
    QSPI reads.  After the run, SpiMonitor's transaction list is checked against
    the golden image via Scoreboard.

    Coverage sampled for each completed SPI transaction.
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

    # Let the SOC run for a while — it will fetch instructions via spimemio
    await Timer(50_000, units="ns")

    spi_mon.stop()
    cpu_mon.stop()
    flash.stop()

    cocotb.log.info(f"SPI transactions captured: {len(spi_mon.transactions)}")

    for txn in spi_mon.transactions:
        sb.check_spi_read(txn)
        sample_spi_txn(txn)

    errors = sb.all_errors()
    assert not errors, f"Scoreboard mismatches:\n" + "\n".join(str(e) for e in errors)
    cocotb.log.info("SPI burst scoreboard: PASS")


@cocotb.test()
async def test_spi_multiple_burst_lengths(dut):
    """
    Synthesize SpiTransaction objects for burst lengths [1, 2, 4, 8, 16, 32]
    and run them through scoreboard + coverage to exercise all length bins
    without needing the CPU to naturally generate each length.
    """
    sb = Scoreboard(GOLDEN_FLASH)

    for burst_len in [1, 2, 4, 8, 16, 32]:
        data = list(GOLDEN_FLASH[0:burst_len])
        txn = SpiTransaction(
            cmd=0xEB,
            addr=0,
            data=data,
            timestamp_ns=float(burst_len * 100),
            reset_asserted=False
        )
        sb.check_spi_read(txn)
        sample_spi_txn(txn)

    assert not sb.all_errors(), sb.report()
    cocotb.log.info("Coverage bins for all burst lengths sampled")
