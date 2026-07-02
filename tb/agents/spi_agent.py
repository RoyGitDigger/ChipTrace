import cocotb
from cocotb.triggers import RisingEdge, FallingEdge, Edge, Timer
from cocotb.queue import Queue
from dataclasses import dataclass, field
from typing import List


@dataclass
class SpiTransaction:
    cmd: int
    addr: int
    data: List[int]
    timestamp_ns: float
    burst_len: int = 0
    reset_asserted: bool = False

    def __post_init__(self):
        self.burst_len = len(self.data)


class SpiFlashModel:
    """
    Passive SPI flash slave. Responds to the QSPI read command (0xEB) that
    spimemio.v issues when the CPU fetches from the 0x01000000 range.

    Protocol handled:
        - Standard SPI mode (single-lane) for command byte and address
        - Quad-IO read (0xEB): command on IO0, address on all 4 bits,
          4 dummy cycles, then data clocked out on all 4 lines

    The model drives flash_io lines through the tristate bus in top_tb.v
    so the DUT sees real signal levels.
    """

    def __init__(self, dut, flash_image: bytes):
        self.dut = dut
        self._image = bytearray(flash_image)
        self.tx_queue = Queue()
        self._running = False

    def load_image(self, data: bytes):
        self._image = bytearray(data)

    def start(self):
        self._running = True
        cocotb.start_soon(self._serve())

    def stop(self):
        self._running = False

    async def _serve(self):
        while self._running:
            await FallingEdge(self.dut.flash_csb)
            await self._handle_transaction()

    async def _handle_transaction(self):
        t0 = cocotb.utils.get_sim_time("ns")
        cmd = await self._rx_byte_single()

        if cmd == 0xEB:
            addr = await self._rx_addr_quad()
            # 4 dummy cycles
            for _ in range(4):
                await RisingEdge(self.dut.flash_clk)

            data_bytes = []
            while int(self.dut.flash_csb.value) == 0:
                b = await self._tx_byte_quad(self._image[addr % len(self._image)])
                data_bytes.append(b)
                addr += 1

            txn = SpiTransaction(
                cmd=cmd,
                addr=addr - len(data_bytes),
                data=data_bytes,
                timestamp_ns=t0
            )
            await self.tx_queue.put(txn)
        else:
            # unknown command — just drain until CS goes high
            while int(self.dut.flash_csb.value) == 0:
                await RisingEdge(self.dut.flash_clk)

    async def _rx_byte_single(self):
        val = 0
        for i in range(7, -1, -1):
            await RisingEdge(self.dut.flash_clk)
            bit = int(self.dut.flash_io[0].value)
            val |= (bit << i)
        return val

    async def _rx_addr_quad(self):
        # 24-bit address, 4 bits per clock (6 clocks)
        addr = 0
        for i in range(5, -1, -1):
            await RisingEdge(self.dut.flash_clk)
            nibble = int(self.dut.flash_io.value) & 0xF
            addr |= (nibble << (i * 4))
        return addr

    async def _tx_byte_quad(self, byte_val: int):
        # Drive two nibbles out on IO[3:0] on falling edges
        hi_nibble = (byte_val >> 4) & 0xF
        lo_nibble = byte_val & 0xF
        await FallingEdge(self.dut.flash_clk)
        self.dut.flash_io.value = hi_nibble
        await FallingEdge(self.dut.flash_clk)
        self.dut.flash_io.value = lo_nibble
        return byte_val


class SpiMonitor:
    """
    Passive observer that records completed SPI transactions from the
    SpiFlashModel's tx_queue and timestamps them for the scoreboard.
    """

    def __init__(self, flash_model: SpiFlashModel):
        self._model = flash_model
        self.transactions: List[SpiTransaction] = []
        self._running = False

    def start(self):
        self._running = True
        cocotb.start_soon(self._record())

    def stop(self):
        self._running = False

    async def _record(self):
        while self._running:
            txn = await self._model.tx_queue.get()
            self.transactions.append(txn)
