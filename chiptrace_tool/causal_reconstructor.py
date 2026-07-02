from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class CausalCluster:
    events: List[Dict[str, Any]]
    span_ns: float
    narrative: str
    hazard_type: str = ""


# Signal pairs that, when they change close together, represent a known
# interaction worth flagging in the report.
HAZARD_PAIRS = [
    ("top_tb.resetn",    "top_tb.flash_csb"),
    ("top_tb.mem_valid", "top_tb.flash_csb"),
    ("top_tb.resetn",    "top_tb.mem_valid"),
    ("top_tb.ser_tx",    "top_tb.mem_valid"),
]

HAZARD_DESCRIPTIONS = {
    ("top_tb.resetn",    "top_tb.flash_csb"):  "reset-during-SPI",
    ("top_tb.mem_valid", "top_tb.flash_csb"):  "CPU-access-while-SPI-active",
    ("top_tb.resetn",    "top_tb.mem_valid"):  "reset-during-CPU-access",
    ("top_tb.ser_tx",    "top_tb.mem_valid"):  "UART-tx-during-CPU-access",
}


def _render_narrative(cluster_events):
    parts = []
    for ev in cluster_events:
        sig_short = ev["signal"].split(".")[-1]
        parts.append(f"{ev['signal'].split('.')[-1]}={ev['value']} @t={ev['time']}ns")
    return " | ".join(parts)


def _classify_hazard(signal_set):
    for pair in HAZARD_PAIRS:
        if pair[0] in signal_set and pair[1] in signal_set:
            return HAZARD_DESCRIPTIONS[pair]
    return "multi-signal-interaction"


def reconstruct(events, window_ns=10):
    """
    Group signal change events into temporal clusters.  Any cluster where
    ≥2 distinct signals change within window_ns of each other is flagged
    as a potential causal interaction.

    Returns a list of CausalCluster objects, ordered by time.

    window_ns: maximum gap between consecutive events to still count them
               as part of the same causal cluster.  10ns is roughly one
               clock cycle at 100MHz — tight enough to catch real races,
               loose enough to group multi-signal state transitions.
    """
    if not events:
        return []

    clusters_raw = []
    current = [events[0]]

    for ev in events[1:]:
        if ev["time"] - current[-1]["time"] <= window_ns:
            current.append(ev)
        else:
            clusters_raw.append(current)
            current = [ev]
    clusters_raw.append(current)

    flagged = []
    for group in clusters_raw:
        signal_set = {e["signal"] for e in group}
        if len(signal_set) < 2:
            continue

        span = group[-1]["time"] - group[0]["time"]
        hazard = _classify_hazard(signal_set)
        narrative = _render_narrative(group)
        flagged.append(CausalCluster(
            events=group,
            span_ns=span,
            narrative=narrative,
            hazard_type=hazard
        ))

    return flagged


def merge_with_log(waveform_events, log_entries, window_ns=50):
    """
    Correlate waveform signal-change clusters with log entries that fall
    within window_ns of each cluster's start time.  Annotates each
    CausalCluster with matching log entries for the HTML report.

    Returns a list of (CausalCluster, [matching_log_entries]) tuples.
    """
    clusters = reconstruct(waveform_events, window_ns=10)
    annotated = []
    for cluster in clusters:
        t0 = cluster.events[0]["time"]
        t1 = cluster.events[-1]["time"]
        matching = [
            e for e in log_entries
            if t0 - window_ns <= e["time"] <= t1 + window_ns
        ]
        annotated.append((cluster, matching))
    return annotated
