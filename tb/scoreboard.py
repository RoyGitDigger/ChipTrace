from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SpiTransaction:
    addr: int
    data: bytes
    timestamp_ns: float
    burst_len: int
    reset_asserted: bool = False


@dataclass
class UartTransaction:
    byte_val: int
    timestamp_ns: float
    direction: str  # "tx" or "rx"


class Scoreboard:
    def __init__(self, golden_flash: bytes):
        self.golden_flash = golden_flash
        self.spi_errors = []
        self.uart_errors = []
        self._uart_expected = []

    def expect_uart_bytes(self, seq: list):
        self._uart_expected.extend(seq)

    def check_spi_read(self, txn: SpiTransaction):
        addr = txn.addr
        length = txn.burst_len
        if addr + length > len(self.golden_flash):
            self.spi_errors.append({
                "time": txn.timestamp_ns,
                "msg": f"SPI read addr=0x{addr:08x} len={length} out of flash bounds ({len(self.golden_flash)} bytes)"
            })
            return
        expected = self.golden_flash[addr:addr + length]
        if bytes(txn.data) != bytes(expected):
            self.spi_errors.append({
                "time": txn.timestamp_ns,
                "addr": addr,
                "expected": expected.hex(),
                "actual":   bytes(txn.data).hex()
            })

    def check_uart_byte(self, txn: UartTransaction):
        if not self._uart_expected:
            return
        expected = self._uart_expected.pop(0)
        if txn.byte_val != expected:
            self.uart_errors.append({
                "time":     txn.timestamp_ns,
                "expected": hex(expected),
                "actual":   hex(txn.byte_val)
            })

    def all_errors(self):
        return self.spi_errors + self.uart_errors

    def report(self) -> str:
        if not self.all_errors():
            return "Scoreboard: PASS — no mismatches"
        lines = [f"Scoreboard: {len(self.all_errors())} error(s)"]
        for e in self.all_errors():
            lines.append(f"  t={e.get('time')}ns {e}")
        return "\n".join(lines)
