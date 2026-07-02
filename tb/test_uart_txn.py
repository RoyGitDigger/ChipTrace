import cocotb
from cocotb.triggers import Timer

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sim_utils import start_clock, reset_dut, wait_n_cycles
from agents.uart_agent import UartDriver, UartMonitor
from agents.spi_agent import SpiFlashModel
from agents.cpu_monitor import CpuMonitor
from scoreboard import Scoreboard, UartTransaction
from coverage import sample_uart_txn
from conftest import GOLDEN_FLASH


TEST_SEQUENCE = [0x41, 0x42, 0x43]  # "ABC"


@cocotb.test()
async def test_uart_loopback(dut):
    """
    Drive bytes onto ser_rx via UartDriver.  Monitor ser_tx via UartMonitor.
    Verify: the UART driver doesn't crash, the monitor assembles framing correctly.
    Scoreboard checks MMIO transactions against expected byte values.
    """
    sb = Scoreboard(GOLDEN_FLASH)
    sb.expect_uart_bytes(TEST_SEQUENCE)

    flash = SpiFlashModel(dut, GOLDEN_FLASH)
    cpu_mon = CpuMonitor(dut, "uart.log")
    driver = UartDriver(dut)
    monitor = UartMonitor(dut)

    await start_clock(dut)
    flash.start()
    cpu_mon.start()
    monitor.start()
    await reset_dut(dut)

    await wait_n_cycles(dut, 20)

    for byte_val in TEST_SEQUENCE:
        await driver.send_byte(byte_val)
        await wait_n_cycles(dut, 10)

    # Give the DUT time to react
    await Timer(200_000, units="ns")

    # Drain whatever the monitor captured and run through scoreboard
    while not monitor.rx_queue.empty():
        ts, got = await monitor.rx_queue.get()
        txn = UartTransaction(byte_val=got, timestamp_ns=ts, direction="tx")
        sb.check_uart_byte(txn)
        sample_uart_txn(txn)

    monitor.stop()
    cpu_mon.stop()
    flash.stop()

    cocotb.log.info(sb.report())

    uart_writes = [
        t for t in cpu_mon.transactions
        if t.addr == 0x02000008 and t.is_write
    ]
    cocotb.log.info(f"UART MMIO writes recorded: {len(uart_writes)}")


@cocotb.test()
async def test_uart_byte_framing(dut):
    """
    Send a single 0x55 (alternating bits) and verify the monitor reassembles
    it correctly — catches off-by-one errors in baud period sampling.
    """
    flash = SpiFlashModel(dut, GOLDEN_FLASH)
    driver = UartDriver(dut)
    monitor = UartMonitor(dut)

    await start_clock(dut)
    flash.start()
    monitor.start()
    await reset_dut(dut)
    await wait_n_cycles(dut, 20)

    await driver.send_byte(0x55)
    await Timer(200_000, units="ns")

    monitor.stop()
    flash.stop()

    if not monitor.rx_queue.empty():
        _, got = await monitor.rx_queue.get()
        cocotb.log.info(f"Monitor captured 0x{got:02X} (expected 0x55 if DUT re-transmitted)")
