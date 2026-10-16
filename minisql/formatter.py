def format_result(result):
    """Format a Result as a text table, similar to psql."""
    headers = [str(c) for c in result.columns]
    rows = [["NULL" if v is None else str(v) for v in row] for row in result.rows]

    # width of each column = the longest value in it
    widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(value))

    def format_line(values):
        return " | ".join(v.ljust(w) for v, w in zip(values, widths))

    lines = [format_line(headers), "-+-".join("-" * w for w in widths)]
    lines += [format_line(row) for row in rows]
    count = len(rows)
    lines.append(f"({count} row{'' if count == 1 else 's'})")
    return "\n".join(lines)