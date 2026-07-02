import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def start_clock(dut, period_ns=10):
    cocotb.start_soon(Clock(dut.clk, period_ns, units="ns").start())
    await RisingEdge(dut.clk)


async def reset_dut(dut, cycles=8):
    dut.resetn.value = 0
    dut.ser_rx.value = 1
    dut.iomem_ready.value = 0
    dut.iomem_rdata.value = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
    dut.resetn.value = 1


async def wait_n_cycles(dut, n):
    for _ in range(n):
        await RisingEdge(dut.clk)


async def wait_signal_high(dut, signal, timeout_cycles=5000):
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk)
        if signal.value == 1:
            return True
    return False


def sim_time_ns():
    return cocotb.utils.get_sim_time("ns")
