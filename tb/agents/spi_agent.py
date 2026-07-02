import cocotb
from cocotb.triggers import RisingEdge, FallingEdge
from cocotb.queue import Queue
from dataclasses import dataclass
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
        - Standard SPI mode (single-lane) for command byte on flash_io_do[0]
        - Quad-IO read (0xEB): address on all 4 bits, Mode byte (2 clocks),
          8 dummy cycles, then data clocked out on flash_io_di[3:0]
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
        self.dut.flash_io_di.value = 0
        cocotb.start_soon(self._serve())

    def stop(self):
        self._running = False

    async def _serve(self):
        while self._running:
            await FallingEdge(self.dut.flash_csb)
            await self._handle_transaction()

    async def _handle_transaction(self):
        t0 = cocotb.utils.get_sim_time("ns")
        try:
            cmd = await self._rx_byte_single()
            if int(self.dut.flash_csb.value) == 1:
                return

            if cmd == 0xEB:
                addr = await self._rx_addr_quad()
                if int(self.dut.flash_csb.value) == 1:
                    return

                # Read Mode byte (2 nibbles = 2 clocks in QSPI)
                mode = 0
                for _ in range(2):
                    await RisingEdge(self.dut.flash_clk)
                    if int(self.dut.flash_csb.value) == 1:
                        return
                    nibble = int(self.dut.flash_io_do.value) & 0xF
                    mode = (mode << 4) | nibble

                # 8 dummy cycles (default config_dummy = 8)
                for _ in range(8):
                    await RisingEdge(self.dut.flash_clk)
                    if int(self.dut.flash_csb.value) == 1:
                        return

                data_bytes = []
                while int(self.dut.flash_csb.value) == 0:
                    b = await self._tx_byte_quad(self._image[addr % len(self._image)])
                    if int(self.dut.flash_csb.value) == 1:
                        break
                    data_bytes.append(b)
                    addr += 1

                if data_bytes:
                    txn = SpiTransaction(
                        cmd=cmd,
                        addr=addr - len(data_bytes),
                        data=data_bytes,
                        timestamp_ns=t0
                    )
                    await self.tx_queue.put(txn)
            else:
                while int(self.dut.flash_csb.value) == 0:
                    await RisingEdge(self.dut.flash_clk)
        finally:
            self.dut.flash_io_di.value = 0

    async def _rx_byte_single(self):
        val = 0
        for i in range(7, -1, -1):
            await RisingEdge(self.dut.flash_clk)
            if int(self.dut.flash_csb.value) == 1:
                return 0
            bit = int(self.dut.flash_io_do[0].value)
            val |= (bit << i)
        return val

    async def _rx_addr_quad(self):
        addr = 0
        for i in range(5, -1, -1):
            await RisingEdge(self.dut.flash_clk)
            if int(self.dut.flash_csb.value) == 1:
                return 0
            nibble = int(self.dut.flash_io_do.value) & 0xF
            addr |= (nibble << (i * 4))
        return addr

    async def _tx_byte_quad(self, byte_val: int):
        hi_nibble = (byte_val >> 4) & 0xF
        lo_nibble = byte_val & 0xF

        await FallingEdge(self.dut.flash_clk)
        if int(self.dut.flash_csb.value) == 1:
            return byte_val
        self.dut.flash_io_di.value = hi_nibble

        await FallingEdge(self.dut.flash_clk)
        if int(self.dut.flash_csb.value) == 1:
            return byte_val
        self.dut.flash_io_di.value = lo_nibble

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
