"""De-rotation helpers for 90°/diagonal chart-label text (WER p3, SLTDA p4).

`connected_labels` clusters chars into labels via connected components in
(x, y) — robust to vertical AND diagonal label orientation — and returns each
label with its x-centre so callers can pair value labels to axis labels by
column proximity."""

from collections import defaultdict


def connected_labels(
    chars: list[dict], dx: float = 6.0, dy: float = 11.0
) -> list[dict]:
    """→ [{text, x, y}] where x/y are the label's mean char centre."""
    pts = [
        {"x": (c["x0"] + c["x1"]) / 2, "y": c["top"], "t": c["text"]}
        for c in chars
    ]
    n = len(pts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if abs(pts[i]["x"] - pts[j]["x"]) <= dx and abs(pts[i]["y"] - pts[j]["y"]) <= dy:
                parent[find(i)] = find(j)

    groups: dict[int, list[dict]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(pts[i])

    labels = []
    for group in groups.values():
        group.sort(key=lambda c: (-c["y"], c["x"]))  # bottom-to-top, then left-to-right
        labels.append(
            {
                "text": "".join(c["t"] for c in group),
                "x": sum(c["x"] for c in group) / len(group),
                "y": sum(c["y"] for c in group) / len(group),
                "n": len(group),
            }
        )

    # second pass: some labels render horizontally with wide per-char kerning,
    # which the CC pass splits into 1–2 char fragments — merge fragments that
    # align on y into left-to-right strings.
    fragments = sorted((l for l in labels if l["n"] <= 2), key=lambda l: (round(l["y"]), l["x"]))
    merged: list[dict] = []
    used: set[int] = set()
    for i, frag in enumerate(fragments):
        if i in used:
            continue
        chain = [frag]
        for j in range(i + 1, len(fragments)):
            if j in used:
                continue
            nxt = fragments[j]
            if abs(nxt["y"] - chain[-1]["y"]) <= 2.5 and 0 < nxt["x"] - chain[-1]["x"] <= 10:
                chain.append(nxt)
                used.add(j)
        if len(chain) > 1:
            used.add(i)
            merged.append(
                {
                    "text": "".join(c["text"] for c in chain),
                    "x": sum(c["x"] for c in chain) / len(chain),
                    "y": chain[0]["y"],
                    "n": sum(c["n"] for c in chain),
                }
            )
    survivors = [l for idx, l in enumerate(fragments) if idx not in used]
    return [l for l in labels if l["n"] > 2] + survivors + merged
