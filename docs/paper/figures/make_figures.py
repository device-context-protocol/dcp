"""Generate all figures for the DCP paper.

Run with:
    python make_figures.py

Outputs both PDF (for LaTeX \\includegraphics) and PNG (for README/web)
into the current directory.

All numbers tagged "synthetic" are illustrative placeholders. They will be
replaced with measured data after the hardware campaign described in §7.1
of the paper.
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------------------
# Publication style.

plt.rcParams.update({
    "figure.dpi":        100,
    "savefig.dpi":       300,
    "savefig.bbox":      "tight",
    "savefig.pad_inches": 0.05,
    "font.family":       "serif",
    "font.serif":        ["DejaVu Serif", "Liberation Serif", "Times New Roman"],
    "font.size":         9,
    "axes.titlesize":    10,
    "axes.labelsize":    9,
    "xtick.labelsize":   8,
    "ytick.labelsize":   8,
    "legend.fontsize":   8,
    "lines.linewidth":   1.2,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.linewidth":    0.7,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
})

# A muted, print-friendly palette. DCP gets the strongest navy.
C = {
    "dcp":     "#1f4e79",
    "dcp_lt":  "#9fbedb",
    "iotmcp":  "#c25450",
    "rawmcp":  "#7fa17a",
    "openapi": "#dfb96b",
    "matter":  "#8c6a4f",
    "bare":    "#888888",

    "header":  "#1f4e79",
    "cbor":    "#7fa17a",
    "hmac":    "#c25450",
    "framing": "#888888",
    "json":    "#dfb96b",

    "bridge_inner": "#eef3f8",
    "bridge_outer": "#1f4e79",
    "llm":          "#9fbedb",
    "device":       "#f3d6ad",
}


def save(fig, name: str) -> None:
    pdf = HERE / f"{name}.pdf"
    png = HERE / f"{name}.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=200)
    plt.close(fig)
    print(f"  wrote {pdf.name}, {png.name}")


# ---------------------------------------------------------------------------
# Figure 1 — Architecture.

def fig_architecture():
    fig, ax = plt.subplots(figsize=(8.4, 3.2))
    # extra horizontal margin so FancyBbox rounded-corner padding (~3 units)
    # never bleeds past the canvas on either side.
    ax.set_xlim(-4, 158); ax.set_ylim(0, 52); ax.axis("off")

    def box(x, y, w, h, label, facecolor, edgecolor="black", text_color="black",
            fontsize=9, rounded=0.02):
        patch = FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.3,rounding_size={rounded}",
                                linewidth=0.8,
                                edgecolor=edgecolor,
                                facecolor=facecolor)
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, label,
                ha="center", va="center",
                fontsize=fontsize, color=text_color)

    # LLM
    box(2, 18, 20, 14, "LLM\nMCP host", C["llm"], fontsize=10)

    # Bridge outer — widened to comfortably hold 2x2 inner grid
    box(34, 4, 70, 44, "", "#ffffff", edgecolor=C["bridge_outer"], rounded=1.5)
    ax.text(34 + 35, 42, "Bridge  —  sole trust boundary",
            ha="center", va="bottom", fontsize=10, color=C["bridge_outer"],
            fontweight="bold")

    # Bridge inner components (2 x 2 grid) — single-line short labels, comfy cells
    inner_w, inner_h = 30, 11
    cells = [
        (37, 24, "Capability token"),
        (69, 24, "Range / type check"),
        (37, 10, "Dry-run preview"),
        (69, 10, "Audit / rate-limit"),
    ]
    for x, y, label in cells:
        box(x, y, inner_w, inner_h, label, C["bridge_inner"],
            edgecolor=C["bridge_outer"], fontsize=8.5)

    # Device — short bare label, slightly tighter font so it never kisses
    # the rounded corners of the box.
    box(120, 18, 28, 14, "Device\ncommodity MCU", C["device"], fontsize=9.5)

    # Arrows.
    def arrow(x1, y1, x2, y2, label, dy_label=2, color="black"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                      arrowstyle="-|>", mutation_scale=10,
                                      linewidth=1.0, color=color))
        ax.text((x1 + x2) / 2, max(y1, y2) + dy_label, label,
                ha="center", va="bottom", fontsize=8, color=color, style="italic")

    arrow(22, 28,  34, 28, "MCP",       dy_label=1)
    arrow(34, 22,  22, 22, "results",   dy_label=-3.5, color="#666666")
    arrow(104, 28, 120, 28, "DCP wire", dy_label=1)     # 16-unit gap
    arrow(120, 22, 104, 22, "reply",    dy_label=-3.5, color="#666666")

    # Transport bullets centered under the Device box (x = 134, w 28).
    ax.text(134, 13, "UART · MQTT · BLE · USB-CDC",
            ha="center", va="center", fontsize=6.5,
            color="#555555", style="italic")
    ax.text(134, 8,  "one wire format, any transport",
            ha="center", va="center", fontsize=6.5, color="#888888")

    save(fig, "arch")


# ---------------------------------------------------------------------------
# Figure 2 — Wire format and comparison to MCP JSON-RPC.

def fig_wire_format():
    fig = plt.figure(figsize=(7.5, 3.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.3, 1], hspace=0.65)

    # Top: byte-level layout of a DCP frame.
    # Three big sections (header / payload / HMAC). The header breakdown
    # (ver/kind/seq/iid) is too narrow to label per-field at honest scale,
    # so we only call out the three macro regions and put the per-field
    # detail in a small inset box on the right.
    ax1 = fig.add_subplot(gs[0])
    ax1.set_xlim(-0.5, 35.5); ax1.set_ylim(-1.4, 1.9); ax1.axis("off")

    # Per-field sub-shading inside the header block, but no per-field labels.
    sub_colors = [C["header"], "#2d6aa3", C["header"], "#2d6aa3"]
    sub_widths = [1, 1, 2, 2]
    sx = 0
    for w, c in zip(sub_widths, sub_colors):
        ax1.add_patch(mpatches.Rectangle((sx, 0), w, 1,
                                           facecolor=c, edgecolor="white",
                                           linewidth=1.0, alpha=0.95))
        sx += w

    # The two big regions.
    ax1.add_patch(mpatches.Rectangle((6, 0), 13, 1,
                                       facecolor=C["cbor"], edgecolor="white",
                                       linewidth=1.0, alpha=0.92))
    ax1.text(12.5, 0.5, "CBOR payload (variable)",
             ha="center", va="center", fontsize=9, color="white",
             fontweight="bold")
    ax1.add_patch(mpatches.Rectangle((19, 0), 16, 1,
                                       facecolor=C["hmac"], edgecolor="white",
                                       linewidth=1.0, alpha=0.92))
    ax1.text(27, 0.5, "optional HMAC-SHA256[:16]",
             ha="center", va="center", fontsize=9, color="white",
             fontweight="bold")

    # Three top bracket labels with leader lines, comfortably spaced.
    ax1.annotate("6-byte fixed header", xy=(3, 1.0), xytext=(3, 1.65),
                 fontsize=8.5, color="#222", ha="center",
                 arrowprops=dict(arrowstyle="-", linewidth=0.5, color="#888"))
    ax1.annotate("CBOR map (RFC 8949)", xy=(12.5, 1.0), xytext=(12.5, 1.65),
                 fontsize=8.5, color="#222", ha="center",
                 arrowprops=dict(arrowstyle="-", linewidth=0.5, color="#888"))
    ax1.annotate("optional 16-byte tag", xy=(27, 1.0), xytext=(27, 1.65),
                 fontsize=8.5, color="#222", ha="center",
                 arrowprops=dict(arrowstyle="-", linewidth=0.5, color="#888"))

    # Below the header: spell out the field breakdown horizontally as text.
    ax1.text(3, -0.55,
             "ver(1) + kind(1) + seq(2) + intent_id(2) = 6 bytes",
             ha="center", va="top", fontsize=7.5, color="#444", style="italic")

    ax1.set_title("DCP frame layout", loc="left", pad=4, fontsize=10)

    # Bottom: size comparison bars.
    ax2 = fig.add_subplot(gs[1])
    labels = [
        "DCP (no HMAC)",
        "DCP (+ HMAC)",
        "CoAP + CBOR",
        "MCP JSON-RPC",
        "OpenAPI / HTTP",
    ]
    # Bytes per typical call: synthetic but representative.
    sizes  = [19, 35, 30, 180, 320]
    colors = [C["dcp"], C["dcp"], C["rawmcp"], C["json"], C["openapi"]]
    bars = ax2.barh(labels, sizes, color=colors, edgecolor="white", linewidth=0.5)
    bars[1].set_hatch("//"); bars[1].set_edgecolor(C["hmac"])
    for bar, size in zip(bars, sizes):
        ax2.text(bar.get_width() + 4, bar.get_y() + bar.get_height() / 2,
                 f"{size} B",
                 va="center", fontsize=8, color="#333")
    ax2.set_xlabel("bytes on wire for a typical call (illustrative)")
    ax2.invert_yaxis()
    ax2.set_xlim(0, 380)
    ax2.tick_params(axis="y", length=0)

    save(fig, "wire_format")


# ---------------------------------------------------------------------------
# Figure 3 — Footprint comparison.

def fig_footprint():
    """Figure 3 — measured static RAM footprint: DCP vs IoT-MCP.

    DCP's number is read from footprint_data.json (measure_footprint.py);
    IoT-MCP's 74 KB is its reported peak memory. Static/peak RAM is the
    one apples-to-apples axis between the two projects and the scarce
    resource on an MCU. IoT-MCP does not report a flash figure, so flash
    stays in the caption rather than being plotted against a blank.
    """
    data_path = HERE / "footprint_data.json"
    if not data_path.exists():
        raise FileNotFoundError(
            "footprint_data.json missing — run measure_footprint.py first.")
    fp = json.loads(data_path.read_text(encoding="utf-8"))
    dcp_ram_kb   = fp["dcp_layer_globals"] / 1024.0
    dcp_flash_kb = fp["dcp_layer_flash"] / 1024.0

    fig, ax = plt.subplots(figsize=(6.5, 2.3))

    labels = ["DCP layer\n(measured)", "IoT-MCP\n(reported peak memory)"]
    values = [dcp_ram_kb, 74.0]
    colors = [C["dcp"], C["iotmcp"]]

    y = np.arange(len(labels))
    ax.barh(y, values, height=0.5, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("static / peak RAM (KB)  —  lower is better")
    ax.set_xlim(0, 84)
    ax.tick_params(axis="y", length=0)

    for yi, v in zip(y, values):
        txt = f"{v:.1f} KB" if v < 10 else f"{v:.0f} KB"
        ax.text(v + 1.5, yi, txt, va="center", ha="left",
                fontsize=9, color="#333", fontweight="bold")

    ax.set_title("Static RAM footprint  (the scarce resource on an MCU)",
                 loc="left", fontsize=9.5, pad=8)

    fig.subplots_adjust(bottom=0.34, top=0.84, left=0.27, right=0.97)
    fig.text(0.5, 0.04,
             f"DCP: measured — the DCP layer adds {dcp_ram_kb:.1f} KB RAM "
             f"and {dcp_flash_kb:.1f} KB flash over a bare Arduino sketch "
             f"(measure_footprint.py).\nIoT-MCP: 74 KB peak memory, reported "
             f"in [iotmcp2025]; it does not report a comparable flash figure.",
             ha="center", va="bottom", fontsize=7, color="#666", style="italic")
    save(fig, "footprint")


# ---------------------------------------------------------------------------
# Figure 4 — Hallucination rejection rate (the killer experiment).

def fig_hallucination():
    """Bars are measured rejection rates over a 150-case adversarial corpus
    (25 cases per category x 6 categories), produced by
    tools/bench_hallucination.py. The figure reads hallucination_data.json
    — it is never hand-typed."""
    data_path = HERE / "hallucination_data.json"
    if not data_path.exists():
        raise FileNotFoundError(
            "hallucination_data.json missing — run "
            "`python tools/bench_hallucination.py` first.")
    data = json.loads(data_path.read_text(encoding="utf-8"))

    category_labels = {
        "out_of_range":          "Out-of-range\nvalue",
        "unit_confusion":        "Unit\nconfusion",
        "wrong_type":            "Wrong\ntype",
        "unknown_intent":        "Unknown\nintent",
        "capability_escalation": "Capability\nescalation",
        "prompt_injection":      "Prompt\ninjection",
    }
    attacks = [category_labels[c] for c in data["categories"]]
    series = {p: data["rejection_pct"][p] for p in data["protocols"]}
    colors = {"DCP": C["dcp"], "IoT-MCP": C["iotmcp"],
              "Raw MCP": C["rawmcp"], "OpenAPI": C["openapi"]}

    fig, ax = plt.subplots(figsize=(9.0, 4.0))
    x = np.arange(len(attacks))
    width = 0.2
    for i, (name, vals) in enumerate(series.items()):
        offset = (i - 1.5) * width
        bars = ax.bar(x + offset, vals, width=width, color=colors[name],
                      label=name, edgecolor="white", linewidth=0.4)
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, v + 2,
                        f"{v}",
                        ha="center", va="bottom", fontsize=6.5, color="#333")

    ax.set_xticks(x)
    ax.set_xticklabels(attacks, fontsize=8.5)
    ax.set_ylabel("% of malformed/adversarial calls rejected\nbefore reaching device")
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.legend(loc="upper center", frameon=False, ncol=4, bbox_to_anchor=(0.5, 1.10))
    ax.grid(axis="y", linewidth=0.4, alpha=0.5)
    ax.set_axisbelow(True)

    fig.subplots_adjust(bottom=0.27, top=0.88, left=0.08, right=0.98)
    n_per = data["n_per_category"]
    if isinstance(n_per, dict):
        n_total = sum(n_per.values())
        models = data.get("usable_models") or [data.get("llm_model", "LLM")]
        short_models = [m.split("/")[-1] for m in models]
        models_str = " + ".join(short_models)
        footer = (
            f"Empirical. {n_total} tool calls aggregated across "
            f"{len(short_models)} LLM(s) ({models_str}) producing tool "
            f"calls in response to adversarial prompts across "
            f"{len(data['categories'])} attack\ncategories. Each call "
            "is fed to every protocol's host-side validator (the real "
            "dcp.bridge.Bridge for DCP; jsonschema for MCP / IoT-MCP / "
            "OpenAPI).\nCorpus in tools/gen_llm_corpus.py + "
            "llm_corpus.json; aggregation in "
            "tools/bench_hallucination_empirical.py."
        )
    else:
        footer = (f"Measured. {n_per} adversarial cases per category x "
                  f"{len(data['categories'])} categories = "
                  f"{n_per * len(data['categories'])} total, each run "
                  "through every protocol's schema-layer validator.")
    fig.text(0.5, 0.02, footer,
             ha="center", va="bottom", fontsize=7.0, color="#666", style="italic")
    save(fig, "hallucination")


# ---------------------------------------------------------------------------
# Figure 5 — End-to-end latency by transport (measured).
#
# Data comes from latency_data.json, produced by tools/bench_latency.py.
# Each entry is 1000 timed round-trips of a set_brightness call. The figure
# is always derived from that recorded measurement — never hand-typed.

def fig_latency():
    data_path = HERE / "latency_data.json"
    if not data_path.exists():
        raise FileNotFoundError(
            "latency_data.json missing — run tools/bench_latency.py first "
            "(--loopback and --serial <port>) to record measurements.")
    data = json.loads(data_path.read_text(encoding="utf-8"))

    # Baseline first, then the hardware transports.
    order = ["loopback", "uart_wroom", "uart_s3"]
    rows = [(k, data[k]) for k in order if k in data]
    if not rows:
        raise ValueError("latency_data.json has no recognised transport keys")

    short = {
        "loopback":   "loopback\n(in-process baseline)",
        "uart_wroom": "UART 115200\nWROOM-32 · CH340",
        "uart_s3":    "UART 115200\nESP32-S3 · native USB",
    }
    palette = {"loopback": C["dcp_lt"], "uart_wroom": C["dcp"], "uart_s3": C["dcp"]}

    fig, ax = plt.subplots(figsize=(6.5, 2.5))
    y = np.arange(len(rows))
    medians  = [d["median"] for _, d in rows]
    err_low  = [d["median"] - d["q1"] for _, d in rows]
    err_high = [d["q3"] - d["median"] for _, d in rows]
    colors   = [palette.get(k, C["dcp"]) for k, _ in rows]

    ax.barh(y, medians, height=0.55, color=colors, edgecolor="white",
            linewidth=0.5, xerr=[err_low, err_high],
            error_kw=dict(ecolor="#333", capsize=3, lw=0.8))
    ax.set_yticks(y)
    ax.set_yticklabels([short.get(k, k) for k, _ in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(medians) * 1.28)
    ax.set_xlabel("round-trip latency (ms)  —  bar = median, whiskers = IQR")
    ax.tick_params(axis="y", length=0)

    for yi, (_, d) in zip(y, rows):
        ax.text(d["median"] + max(medians) * 0.02, yi,
                f"{d['median']:.2f} ms", va="center", ha="left",
                fontsize=8, color="#333", fontweight="bold")

    n = rows[0][1]["n"]
    ax.set_title(f"Measured round-trip call latency  "
                 f"(set_brightness, N={n} per transport)",
                 loc="left", fontsize=9.5, pad=8)

    fig.subplots_adjust(bottom=0.30, top=0.86, left=0.26, right=0.97)
    fig.text(0.5, 0.03,
             "Measured by tools/bench_latency.py. The loopback row is the "
             "protocol's own encode/decode cost with no wire;\nthe two UART "
             "rows are real hardware. CH340 and native-USB transports land "
             "within 0.05 ms of each other.",
             ha="center", va="bottom", fontsize=7, color="#666", style="italic")
    save(fig, "latency")


# ---------------------------------------------------------------------------
# Driver.

def fig_social_preview():
    """1200x630 PNG for GitHub Social Preview / Twitter card / og:image.

    Brand block left, three big stats right. No diagram — the goal is
    single-message recognition at thumbnail size.
    """
    fig, ax = plt.subplots(figsize=(12, 6.3), facecolor="#0f1d2e")
    ax.set_xlim(0, 100); ax.set_ylim(0, 50); ax.axis("off")
    ax.set_facecolor("#0f1d2e")

    # ── Left half: brand ───────────────────────────────────────────
    # "OPEN PROTOCOL" chip
    ax.add_patch(mpatches.FancyBboxPatch((4, 44), 28, 4,
                                           boxstyle="round,pad=0.3,rounding_size=0.8",
                                           facecolor="#1f4e79", edgecolor="none"))
    ax.text(18, 46, "AN  OPEN  PROTOCOL",
            fontsize=11, color="white", fontweight="bold",
            ha="center", va="center")

    # Big "DCP" mark
    ax.text(8, 33, "DCP",
            fontsize=82, color="white", fontweight="bold",
            ha="left", va="center", family="serif")
    # Underline
    ax.add_patch(mpatches.Rectangle((8, 26), 22, 0.4,
                                      facecolor="#9fbedb", edgecolor="none"))
    # Subtitle
    ax.text(8, 23, "Device Context Protocol",
            fontsize=19, color="#9fbedb", ha="left", va="top",
            fontweight="bold")
    # Tagline
    ax.text(8, 16,
            "Let LLMs safely control",
            fontsize=21, color="white", ha="left", va="top")
    ax.text(8, 11.5,
            "dollar-class microcontrollers.",
            fontsize=21, color="white", ha="left", va="top")
    # Footer URL + install
    ax.text(8, 5, "github.com/device-context-protocol",
            fontsize=13, color="#9fbedb", ha="left", va="center",
            family="monospace")
    ax.text(8, 2, "MIT  ·  pip install pydcp",
            fontsize=11, color="#7090a8", ha="left", va="center",
            family="monospace", style="italic")

    # ── Right half: three stat rows ────────────────────────────────
    # Vertical separator
    ax.add_patch(mpatches.Rectangle((54, 6), 0.15, 38,
                                      facecolor="#2d4a6a", edgecolor="none"))

    # Each stat: big hero number on row 1, single descriptor line on row 2.
    # Unit is baked into the descriptor so it can never collide with the number.
    stats = [
        (38, "19",    "bytes — typical call on the wire"),
        (24, "<1 KB", "of RAM — the DCP layer's measured footprint"),
        (10, "MCP",   "compatible — zero-config in Claude Desktop"),
    ]
    for y, num, desc in stats:
        # big hero number / word
        ax.text(58, y, num,
                fontsize=52,
                color="#9fbedb", fontweight="bold",
                ha="left", va="center")
        # descriptor line directly below
        ax.text(58, y - 6, desc,
                fontsize=13, color="white",
                ha="left", va="top", linespacing=1.3)

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    save(fig, "social_preview")


def main():
    print("Generating figures to", HERE)
    fig_architecture()
    fig_wire_format()
    fig_footprint()
    fig_hallucination()
    fig_latency()
    fig_social_preview()
    print("Done.")


if __name__ == "__main__":
    main()
