from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db
import yaml


def _burst_len_bin(txn):
    return txn.burst_len


def _reset_during(txn):
    return txn.reset_asserted


def _uart_class(txn):
    v = txn.byte_val
    if v < 0x20:
        return "control"
    elif v <= 0x7E:
        return "printable"
    else:
        return "high"


@CoverPoint(
    "top.spi_burst_len",
    xf=_burst_len_bin,
    bins=[1, 2, 4, 8, 16, 32],
    bins_labels=["1B", "2B", "4B", "8B", "16B", "32B"]
)
@CoverPoint(
    "top.reset_during_txn",
    xf=_reset_during,
    bins=[False, True],
    bins_labels=["nominal", "reset_injected"]
)
def sample_spi_txn(txn):
    pass


@CoverCross(
    "top.cross_burst_reset",
    items=["top.spi_burst_len", "top.reset_during_txn"]
)
def _cross_dummy():
    pass


@CoverPoint(
    "top.uart_byte_class",
    xf=_uart_class,
    bins=["control", "printable", "high"]
)
def sample_uart_txn(txn):
    pass


def harvest(out_path="coverage.yml"):
    with open(out_path, "w") as f:
        yaml.dump(coverage_db, f, default_flow_style=False)
