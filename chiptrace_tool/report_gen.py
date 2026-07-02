import argparse
import os
import sys
import yaml
from datetime import datetime

try:
    from chiptrace_tool.wave_parser import load_events
    from chiptrace_tool.log_parser import parse_log
    from chiptrace_tool.causal_reconstructor import merge_with_log, CausalCluster
except ImportError:
    from wave_parser import load_events
    from log_parser import parse_log
    from causal_reconstructor import merge_with_log, CausalCluster



_HAZARD_COLOR = {
    "reset-during-SPI":          "#ef4444",
    "CPU-access-while-SPI-active": "#f97316",
    "reset-during-CPU-access":   "#eab308",
    "UART-tx-during-CPU-access": "#3b82f6",
    "multi-signal-interaction":  "#8b5cf6",
}

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    min-height: 100vh;
}
header {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid #334155;
    padding: 24px 40px;
    display: flex;
    align-items: center;
    gap: 16px;
}
header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    background: linear-gradient(90deg, #38bdf8, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
header .subtitle {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 2px;
}
.badge {
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 9999px;
    background: #1e293b;
    border: 1px solid #334155;
    color: #94a3b8;
}
.container { max-width: 1200px; margin: 0 auto; padding: 32px 40px; }
.section-title {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1e293b;
}
.coverage-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
}
.cov-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px;
}
.cov-card .label {
    font-size: 0.8rem;
    color: #94a3b8;
    margin-bottom: 8px;
}
.cov-card .pct {
    font-size: 1.8rem;
    font-weight: 700;
    color: #38bdf8;
    line-height: 1;
}
.bar-track {
    height: 6px;
    background: #0f172a;
    border-radius: 9999px;
    margin-top: 10px;
    overflow: hidden;
}
.bar-fill {
    height: 100%;
    border-radius: 9999px;
    background: linear-gradient(90deg, #38bdf8, #818cf8);
    transition: width 0.3s ease;
}
.timeline { display: flex; flex-direction: column; gap: 12px; margin-bottom: 40px; }
.cluster-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    overflow: hidden;
}
.cluster-card summary {
    list-style: none;
    padding: 16px 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 12px;
    user-select: none;
}
.cluster-card summary::-webkit-details-marker { display: none; }
.cluster-card summary:hover { background: #263044; }
.hazard-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
}
.cluster-card .time-label {
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    color: #64748b;
}
.cluster-card .hazard-label {
    font-size: 0.78rem;
    font-weight: 600;
    flex: 1;
}
.span-badge {
    font-size: 0.68rem;
    color: #64748b;
    padding: 2px 8px;
    background: #0f172a;
    border-radius: 9999px;
}
.cluster-body {
    padding: 0 20px 20px 20px;
    border-top: 1px solid #334155;
}
.event-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
    font-size: 0.78rem;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
.event-table th {
    text-align: left;
    padding: 6px 10px;
    background: #0f172a;
    color: #64748b;
    font-weight: 500;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
}
.event-table td {
    padding: 5px 10px;
    border-bottom: 1px solid #1e293b;
    color: #cbd5e1;
}
.event-table tr:last-child td { border-bottom: none; }
.log-section {
    margin-top: 12px;
    padding: 10px 12px;
    background: #0f172a;
    border-radius: 8px;
    font-size: 0.75rem;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    color: #94a3b8;
    line-height: 1.6;
}
.log-section .log-title {
    font-size: 0.68rem;
    color: #475569;
    margin-bottom: 6px;
    font-family: inherit;
}
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #475569;
}
.empty-state .icon { font-size: 3rem; margin-bottom: 12px; }
.meta-row {
    display: flex;
    gap: 24px;
    margin-bottom: 32px;
    flex-wrap: wrap;
}
.meta-item { font-size: 0.78rem; color: #64748b; }
.meta-item span { color: #94a3b8; }
"""


def _coverage_cards_html(coverage_data):
    if not coverage_data:
        return "<p style='color:#475569;font-size:0.85rem'>No coverage data found.</p>"

    cards = []
    for name, info in coverage_data.items():
        if not isinstance(info, dict):
            continue
        covered = info.get("covered", 0)
        total = info.get("total", 1)
        pct = round((covered / total) * 100) if total else 0
        cards.append(f"""
        <div class="cov-card">
            <div class="label">{name}</div>
            <div class="pct">{pct}%</div>
            <div style="font-size:0.72rem;color:#64748b;margin-top:4px">{covered}/{total} bins hit</div>
            <div class="bar-track">
                <div class="bar-fill" style="width:{pct}%"></div>
            </div>
        </div>""")
    return "\n".join(cards)


def _cluster_card_html(idx, cluster, log_entries):
    color = _HAZARD_COLOR.get(cluster.hazard_type, "#8b5cf6")
    t0 = cluster.events[0]["time"] if cluster.events else 0

    rows = []
    for ev in cluster.events:
        sig_short = ev["signal"].split(".")[-1]
        rows.append(
            f"<tr><td>{ev['time']}</td><td>{sig_short}</td><td>{ev['value']}</td></tr>"
        )

    log_html = ""
    if log_entries:
        lines = []
        for entry in log_entries[:8]:
            fields = " ".join(f"{k}={v}" for k, v in entry["fields"].items())
            lines.append(f"[{entry['time']}ns] {entry['kind']}  {fields}")
        log_html = f"""
        <div class="log-section">
            <div class="log-title">BUS LOG (correlated)</div>
            {"<br>".join(lines)}
        </div>"""

    return f"""
    <details class="cluster-card">
        <summary>
            <div class="hazard-dot" style="background:{color}"></div>
            <div class="time-label">t={t0}ns</div>
            <div class="hazard-label" style="color:{color}">{cluster.hazard_type.replace('-', ' ')}</div>
            <div class="span-badge">span {cluster.span_ns:.0f}ns</div>
        </summary>
        <div class="cluster-body">
            <table class="event-table">
                <thead><tr><th>TIME (ns)</th><th>SIGNAL</th><th>VALUE</th></tr></thead>
                <tbody>{"".join(rows)}</tbody>
            </table>
            {log_html}
        </div>
    </details>"""


def render_html(annotated_clusters, coverage_data, out_path, run_meta=None):
    """
    Render a self-contained HTML report.

    annotated_clusters: list of (CausalCluster, [log_entries]) from causal_reconstructor
    coverage_data: dict loaded from coverage.yml
    out_path: path to write the HTML file
    run_meta: optional dict with keys like 'vcd', 'log', 'timestamp'
    """
    meta = run_meta or {}
    ts = meta.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    vcd = meta.get("vcd", "—")
    log = meta.get("log", "—")
    n_clusters = len(annotated_clusters)

    meta_html = f"""
    <div class="meta-row">
        <div class="meta-item">Run: <span>{ts}</span></div>
        <div class="meta-item">Waveform: <span>{os.path.basename(vcd)}</span></div>
        <div class="meta-item">Log: <span>{os.path.basename(log) if log != '—' else '—'}</span></div>
        <div class="meta-item">Flagged clusters: <span>{n_clusters}</span></div>
    </div>"""

    cov_html = _coverage_cards_html(coverage_data)

    if annotated_clusters:
        timeline_html = "\n".join(
            _cluster_card_html(i, c, l)
            for i, (c, l) in enumerate(annotated_clusters)
        )
    else:
        timeline_html = """
        <div class="empty-state">
            <div class="icon">✓</div>
            <div>No causal interactions flagged — all signal transitions isolated</div>
        </div>"""

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChipTrace — Failure Analysis Report</title>
<meta name="description" content="Automated post-silicon causal timeline reconstruction from waveform and firmware log data.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<header>
    <div>
        <h1>ChipTrace</h1>
        <div class="subtitle">Automated Post-Silicon Root-Cause Reconstruction</div>
    </div>
    <div class="badge">PicoSoC · Verilator · cocotb</div>
</header>
<div class="container">
    {meta_html}
    <div class="section-title">Functional Coverage</div>
    <div class="coverage-grid">
        {cov_html}
    </div>
    <div class="section-title">Causal Timeline — Flagged Signal Interactions</div>
    <div class="timeline">
        {timeline_html}
    </div>
</div>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(
        description="ChipTrace — generate HTML failure analysis report"
    )
    parser.add_argument("--vcd",       required=True,  help="Path to VCD waveform dump")
    parser.add_argument("--log",       default=None,   help="Path to firmware/bus log")
    parser.add_argument("--coverage",  default=None,   help="Path to coverage.yml")
    parser.add_argument("--out",       default="report.html", help="Output HTML path")
    parser.add_argument("--window-ns", type=int, default=10,
                        help="Temporal clustering window in ns (default 10)")
    args = parser.parse_args()

    print(f"[chiptrace] Loading waveform: {args.vcd}")
    events = load_events(args.vcd)
    print(f"[chiptrace] {len(events)} signal change events loaded")

    log_entries = []
    if args.log:
        print(f"[chiptrace] Loading log: {args.log}")
        log_entries = parse_log(args.log)
        print(f"[chiptrace] {len(log_entries)} log entries parsed")

    annotated = merge_with_log(events, log_entries, window_ns=args.window_ns)
    print(f"[chiptrace] {len(annotated)} causal clusters flagged")

    coverage_data = {}
    if args.coverage and os.path.exists(args.coverage):
        with open(args.coverage) as f:
            coverage_data = yaml.safe_load(f) or {}

    render_html(
        annotated_clusters=annotated,
        coverage_data=coverage_data,
        out_path=args.out,
        run_meta={
            "vcd":       args.vcd,
            "log":       args.log or "—",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )
    print(f"[chiptrace] Report written to: {args.out}")


if __name__ == "__main__":
    main()
