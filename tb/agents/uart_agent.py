import cocotb
from cocotb.triggers import RisingEdge, FallingEdge, Timer
from cocotb.queue import Queue


# 115200 baud at a 10ns clock → period = 1/115200 s ≈ 8681ns
_BAUD_NS = 8681


class UartDriver:
    """
    Drives bytes onto ser_rx (the DUT's receive line) by bit-banging
    at 115200 baud: start bit, 8 data bits LSB-first, stop bit.
    """

    def __init__(self, dut):
        self.dut = dut
        self.dut.ser_rx.value = 1  # line idle high

    async def send_byte(self, val: int):
        bits = [0]  # start
        for i in range(8):
            bits.append((val >> i) & 1)
        bits.append(1)  # stop

        for bit in bits:
            self.dut.ser_rx.value = bit
            await Timer(_BAUD_NS, units="ns")

    async def send_string(self, s: str):
        for ch in s:
            await self.send_byte(ord(ch))


class UartMonitor:
    """
    Passive monitor. Samples ser_tx from the DUT, detects the UART
    framing (start bit → 8 data bits → stop bit), and pushes assembled
    (timestamp_ns, byte_val) tuples onto rx_queue for the test to check.

    Runs as a background coroutine for the lifetime of the test.
    """

    def __init__(self, dut):
        self.dut = dut
        self.rx_queue = Queue()
        self._running = False

    def start(self):
        self._running = True
        cocotb.start_soon(self._sample())

    def stop(self):
        self._running = False

    async def _sample(self):
        while self._running:
            # wait for falling edge on ser_tx (start bit)
            await FallingEdge(self.dut.ser_tx)
            t_start = cocotb.utils.get_sim_time("ns")

            # sit in the middle of the start bit, then sample each data bit
            await Timer(_BAUD_NS // 2, units="ns")

            byte_val = 0
            for i in range(8):
                await Timer(_BAUD_NS, units="ns")
                bit = int(self.dut.ser_tx.value)
                byte_val |= (bit << i)

            # consume stop bit
            await Timer(_BAUD_NS, units="ns")

            await self.rx_queue.put((t_start, byte_val))

    async def expect_byte(self, expected: int, timeout_ns=500_000):
        ts, got = await self.rx_queue.get()
        assert got == expected, (
            f"UART mismatch at t={ts:.0f}ns: expected 0x{expected:02X} got 0x{got:02X}"
        )
        return ts, got
