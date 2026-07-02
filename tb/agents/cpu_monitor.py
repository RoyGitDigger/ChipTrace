import cocotb
from cocotb.triggers import RisingEdge
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BusTransaction:
    timestamp_ns: float
    addr: int
    wdata: Optional[int]
    rdata: Optional[int]
    wstrb: int
    is_write: bool
    is_instr_fetch: bool


class CpuMonitor:
    """
    Passive bus snooper on the PicoRV32 native memory interface.

    Watches mem_valid + mem_ready every rising clock edge. Records every
    completed handshake (valid AND ready both high) as a BusTransaction
    with a sim timestamp. This log is what the causal reconstructor uses
    to detect DMA-vs-CPU ordering races.

    Also writes a plain-text log to uart.log so the chiptrace_tool can
    parse it without needing the full VCD.
    """

    def __init__(self, dut, log_path="uart.log"):
        self.dut = dut
        self.transactions: List[BusTransaction] = []
        self._running = False
        self._log_path = log_path
        self._log_file = None

    def start(self):
        self._running = True
        self._log_file = open(self._log_path, "w")
        cocotb.start_soon(self._snoop())

    def stop(self):
        self._running = False
        if self._log_file:
            self._log_file.close()

    async def _snoop(self):
        while self._running:
            await RisingEdge(self.dut.clk)

            try:
                valid = int(self.dut.mem_valid.value)
                ready = int(self.dut.mem_ready.value)
            except Exception:
                continue

            if valid and ready:
                t = cocotb.utils.get_sim_time("ns")
                addr  = int(self.dut.mem_addr.value)
                wstrb = int(self.dut.mem_wstrb.value)
                is_write = wstrb != 0
                is_fetch = int(self.dut.mem_instr.value) == 1

                wdata = int(self.dut.mem_wdata.value) if is_write else None
                rdata = int(self.dut.mem_rdata.value) if not is_write else None

                txn = BusTransaction(
                    timestamp_ns=t,
                    addr=addr,
                    wdata=wdata,
                    rdata=rdata,
                    wstrb=wstrb,
                    is_write=is_write,
                    is_instr_fetch=is_fetch
                )
                self.transactions.append(txn)

                kind = "IFETCH" if is_fetch else ("WRITE" if is_write else "READ")
                line = f"[{t:.0f}] {kind} addr=0x{addr:08x}"
                if is_write:
                    line += f" wdata=0x{wdata:08x} wstrb=0b{wstrb:04b}"
                else:
                    line += f" rdata=0x{rdata:08x}"
                self._log_file.write(line + "\n")
                self._log_file.flush()
