import pytest
import cocotb
from coverage import harvest


# Synthetic 256-byte flash image used across all tests.
# Bytes 0-3: PicoRV32 reset vector jump instruction (JAL x0, 0 → infinite loop
#            at address 0x01000000, which is where picosoc boots from SPI flash)
# Byte  4+:  Incrementing pattern so any SPI read mismatch is obvious in the log
def _build_flash_image():
    img = bytearray(256)
    # JAL x0, 0  — encodes as 0x6F 0x00 0x00 0x00 in little-endian RISC-V
    img[0] = 0x6F
    img[1] = 0x00
    img[2] = 0x00
    img[3] = 0x00
    for i in range(4, 256):
        img[i] = i & 0xFF
    return bytes(img)


GOLDEN_FLASH_IMAGE = _build_flash_image()


@pytest.fixture(scope="session")
def golden_flash():
    return GOLDEN_FLASH_IMAGE


def pytest_sessionfinish(session, exitstatus):
    try:
        harvest("coverage.yml")
    except Exception:
        pass
