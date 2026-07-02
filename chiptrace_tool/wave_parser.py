import os
from vcdvcd import VCDVCD


# Signals we care about for causal analysis — subset of what Verilator traces.
# These match the hierarchical names as Verilator emits them (top_tb prefix).
DEFAULT_SIGNALS = [
    "top_tb.clk",
    "top_tb.resetn",
    "top_tb.flash_csb",
    "top_tb.flash_clk",
    "top_tb.mem_valid",
    "top_tb.mem_ready",
    "top_tb.mem_addr",
    "top_tb.mem_wstrb",
    "top_tb.ser_tx",
    "top_tb.ser_rx",
]


def load_events(vcd_path, signals=None):
    """
    Parse a VCD file and return a flat, time-sorted list of signal change events.

    Each entry is a dict:
        {
            "time":   int,   # simulation time in the VCD's native timescale units
            "signal": str,   # hierarchical signal name
            "value":  str,   # value as a string ("0", "1", "x", "z", or hex for buses)
        }

    signals: list of signal names to extract.  Defaults to DEFAULT_SIGNALS.
             Pass None to extract everything (can be large).
    """
    if not os.path.exists(vcd_path):
        raise FileNotFoundError(f"VCD file not found: {vcd_path}")

    sig_list = signals or DEFAULT_SIGNALS

    try:
        vcd = VCDVCD(vcd_path, signals=sig_list, store_tvs=True)
    except Exception:
        # If named signals aren't found, fall back to loading all
        vcd = VCDVCD(vcd_path, store_tvs=True)

    events = []
    for ref in vcd.references_to_ids.keys():
        if sig_list and not any(s in ref for s in sig_list):
            continue
        sig_obj = vcd[ref]
        for (time, value) in sig_obj.tv:
            events.append({
                "time":   int(time),
                "signal": ref,
                "value":  str(value)
            })

    events.sort(key=lambda e: e["time"])
    return events
