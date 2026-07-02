import re
import os


# Line format written by CpuMonitor:
#   [142000] IFETCH addr=0x01000000 rdata=0x0000006f
_LINE_RE = re.compile(
    r"^\[(\d+)\]\s+(\w+)\s+(.+)$"
)


def parse_log(log_path):
    """
    Parse the timestamped bus transaction log written by CpuMonitor.

    Returns a list of dicts sorted by timestamp:
        {
            "time":  int,   # nanoseconds
            "kind":  str,   # "IFETCH", "READ", or "WRITE"
            "fields": dict  # parsed key=value pairs from the rest of the line
        }
    """
    if not os.path.exists(log_path):
        return []

    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _LINE_RE.match(line)
            if not m:
                continue
            timestamp = int(m.group(1))
            kind = m.group(2)
            rest = m.group(3)

            fields = {}
            for token in rest.split():
                if "=" in token:
                    k, v = token.split("=", 1)
                    fields[k] = v

            entries.append({
                "time":   timestamp,
                "kind":   kind,
                "fields": fields
            })

    entries.sort(key=lambda e: e["time"])
    return entries
