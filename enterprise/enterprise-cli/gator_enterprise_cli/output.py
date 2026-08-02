"""Output formatting — tables, JSON, key-value pairs."""

import json
import sys


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a formatted ASCII table."""
    if not rows:
        print("(no results)")
        return

    # Compute column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "  ".join("-" * widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)

    # Rows
    for row in rows:
        line = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row) if i < len(widths))
        print(line)


def print_json(data) -> None:
    """Print formatted JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


def print_kv(pairs: list[tuple[str, str]]) -> None:
    """Print key-value pairs."""
    if not pairs:
        return
    max_key = max(len(k) for k, _ in pairs)
    for key, value in pairs:
        print(f"  {key.ljust(max_key)}  {value}")
