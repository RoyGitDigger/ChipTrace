"""
Generates firmware/hello.hex — a synthetic PicoRV32 machine code image
that the testbench loads as the SPI flash content.

The image encodes this assembly:
    # Set up baud rate divisor for 115200 at 100MHz clock:
    li   a0, 0x02000000      # base
    li   a1, 868             # divisor
    sw   a1, 4(a0)           # write divisor to 0x02000004

    # Echo loop:
    loop:
    lw   a2, 8(a0)           # read UART data register at 0x02000008
    li   t0, -1              # no-data value
    beq  a2, t0, loop        # loop if value == -1
    sw   a2, 8(a0)           # echo character back (write to 0x02000008)
    j    loop                # repeat
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
    imm20  = (imm >> 20) & 1
    imm19_12 = (imm >> 12) & 0xFF
    imm11  = (imm >> 11) & 1
    imm10_1 = (imm >> 1) & 0x3FF
    return (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12) | (rd << 7) | opcode

def _btype(opcode, funct3, rs1, rs2, imm):
    # imm[12|10:5|4:1|11]
    imm12 = (imm >> 12) & 1
    imm11 = (imm >> 11) & 1
    imm10_5 = (imm >> 5) & 0x3F
    imm4_1 = (imm >> 1) & 0xF
    return (imm12 << 31) | (imm10_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm4_1 << 8) | (imm11 << 7) | opcode


OPCODE_LUI    = 0x37
OPCODE_ADDI   = 0x13
OPCODE_STORE  = 0x23
OPCODE_JAL    = 0x6F
OPCODE_LOAD   = 0x03
OPCODE_BRANCH = 0x63

# Registers
A0 = 10
A1 = 11
A2 = 12
T0 = 5

instructions = [
    # lui a0, 0x02000  (loads 0x02000000 into a0)
    _utype(OPCODE_LUI, A0, 0x02000),

    # addi a1, x0, 868  (divisor for 115200 baud)
    _itype(OPCODE_ADDI, A1, 0, 0, 868),

    # sw a1, 4(a0)     (write divisor)
    _stype(OPCODE_STORE, 2, A0, A1, 4),

    # loop:
    # lw a2, 8(a0)     (read UART data reg)
    _itype(OPCODE_LOAD, A2, 2, A0, 8),

    # addi t0, x0, -1  (load -1)
    _itype(OPCODE_ADDI, T0, 0, 0, -1),

    # beq a2, t0, -8   (loop if no data)
    _btype(OPCODE_BRANCH, 0, A2, T0, -8),

    # sw a2, 8(a0)     (write echo byte)
    _stype(OPCODE_STORE, 2, A0, A2, 8),

    # jal x0, -16      (repeat loop)
    _jtype(OPCODE_JAL, 0, -16),
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
