"""Shared de-rotation for tables laid out 90°-rotated with individually
positioned glyphs (WER p3, SLTDA p4): cluster pdfplumber chars by x-centre —
each cluster is one visual row — then read each cluster bottom-to-top."""


def derotated_lines(chars: list[dict], x_tol: float = 3.5) -> list[str]:
    clusters: list[dict] = []  # {x, chars: [...]}
    for ch in chars:
        xc = (ch["x0"] + ch["x1"]) / 2
        for cluster in clusters:
            if abs(cluster["x"] - xc) <= x_tol:
                cluster["chars"].append(ch)
                cluster["x"] = (cluster["x"] * (len(cluster["chars"]) - 1) + xc) / len(cluster["chars"])
                break
        else:
            clusters.append({"x": xc, "chars": [ch]})
    clusters.sort(key=lambda c: c["x"])
    lines = []
    for cluster in clusters:
        ordered = sorted(cluster["chars"], key=lambda ch: -ch["top"])  # bottom-to-top
        lines.append("".join(ch["text"] for ch in ordered))
    return lines
