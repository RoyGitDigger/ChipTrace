"""
Generates firmware/hello.hex — a synthetic PicoRV32 machine code image
that the testbench loads as the SPI flash content.

The image encodes this assembly:
    # After reset, picosoc starts execution at 0x00100000 (SRAM copy of flash)
    # We write 'H' (0x48) to the UART data register at 0x02000008

    li   a0, 0x02000000      # UART base
    li   a1, 0x48            # 'H'
    sw   a1, 8(a0)           # *(uart_base + 8) = 'H'  → UART send
    j    0                   # loop forever

RISC-V encoding is little-endian 32-bit words.
"""

import struct
import os

# RISC-V instruction encoding helpers

def _itype(opcode, rd, funct3, rs1, imm):
    imm12 = imm & 0xFFF
    return (imm12 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

def _stype(opcode, funct3, rs1, rs2, imm):
    imm5  = imm & 0x1F
    imm7  = (imm >> 5) & 0x7F
    return (imm7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm5 << 7) | opcode

def _utype(opcode, rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | opcode

def _jtype(opcode, rd, imm):
    # imm[20|10:1|11|19:12]
    imm20  = (imm >> 20) & 1
    imm19_12 = (imm >> 12) & 0xFF
    imm11  = (imm >> 11) & 1
    imm10_1 = (imm >> 1) & 0x3FF
    return (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12) | (rd << 7) | opcode

OPCODE_LUI    = 0x37
OPCODE_ADDI   = 0x13
OPCODE_STORE  = 0x23
OPCODE_JAL    = 0x6F

# Registers
A0, A1 = 10, 11

instructions = [
    # lui a0, 0x02000  (loads 0x02000000 into a0)
    _utype(OPCODE_LUI, A0, 0x02000),

    # addi a1, x0, 0x48  ('H')
    _itype(OPCODE_ADDI, A1, 0, 0, 0x48),

    # sw a1, 8(a0)   → store to 0x02000008 (UART data reg)
    _stype(OPCODE_STORE, 2, A0, A1, 8),

    # jal x0, -4    (jump back 4 bytes = infinite loop at this instruction)
    _jtype(OPCODE_JAL, 0, -4),
]

img = bytearray(256)
offset = 0
for instr in instructions:
    struct.pack_into("<I", img, offset, instr)
    offset += 4

# Fill remainder with incrementing bytes so any read mismatch is obvious
for i in range(offset, 256):
    img[i] = i & 0xFF

out_path = os.path.join(os.path.dirname(__file__), "hello.hex")
with open(out_path, "w") as f:
    for i in range(0, len(img), 16):
        chunk = img[i:i+16]
        hex_bytes = " ".join(f"{b:02X}" for b in chunk)
        f.write(f"{i:04X}: {hex_bytes}\n")

print(f"Written {len(img)} bytes to {out_path}")
print("Instructions encoded:")
for i, instr in enumerate(instructions):
    print(f"  [{i*4:04X}] 0x{instr:08X}")
