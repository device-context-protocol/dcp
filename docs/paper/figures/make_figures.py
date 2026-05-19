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
    fig, ax = plt.subplots(figsize=(8.2, 3.2))
    # extra horizontal margin so FancyBbox rounded-corner padding (~3 units)
    # never bleeds past the canvas on either side.
    ax.set_xlim(-4, 152); ax.set_ylim(0, 52); ax.axis("off")

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

    # Device — short bare label (no parens). Pushed further right so the
    # "DCP wire" label on the incoming arrow has breathing room.
    box(122, 18, 22, 14, "Device\n< 16 KB MCU", C["device"], fontsize=10)

    # Arrows.
    def arrow(x1, y1, x2, y2, label, dy_label=2, color="black"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                      arrowstyle="-|>", mutation_scale=10,
                                      linewidth=1.0, color=color))
        ax.text((x1 + x2) / 2, max(y1, y2) + dy_label, label,
                ha="center", va="bottom", fontsize=8, color=color, style="italic")

    arrow(22, 28,  34, 28, "MCP",       dy_label=1)
    arrow(34, 22,  22, 22, "results",   dy_label=-3.5, color="#666666")
    arrow(104, 28, 122, 28, "DCP wire", dy_label=1)     # 18-unit gap (was 12)
    arrow(122, 22, 104, 22, "reply",    dy_label=-3.5, color="#666666")

    # Transport bullets centered under the Device box (x ≈ 133, w 22).
    # Shortened slightly so the line is roughly the Device's width.
    ax.text(133, 13, "UART · MQTT · BLE · USB-CDC",
            ha="center", va="center", fontsize=6.5,
            color="#555555", style="italic")
    ax.text(133, 8,  "one wire format, any transport",
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
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.8))

    protocols = ["DCP\n(target)", "IoT-MCP\n[ref]", "Direct\nMCP", "Matter\n(typical)"]
    flash_kb  = [16, 74, 120, 256]
    ram_kb    = [2,  18, 40,  80]
    colors    = [C["dcp"], C["iotmcp"], C["rawmcp"], C["matter"]]

    for ax, data, label, ymax in [
        (axes[0], flash_kb, "Flash (KB)", 300),
        (axes[1], ram_kb,   "RAM (KB)",   100),
    ]:
        bars = ax.bar(protocols, data, color=colors, edgecolor="white", linewidth=0.5)
        bars[0].set_hatch("//"); bars[0].set_edgecolor("white")
        for bar, val in zip(bars, data):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + ymax * 0.02,
                    f"{val}",
                    ha="center", va="bottom", fontsize=8, color="#333")
        ax.set_ylabel(label)
        ax.set_ylim(0, ymax)
        ax.tick_params(axis="x", length=0)

    fig.suptitle("Reference-implementation memory footprint  (DCP target, others measured/typical)",
                 fontsize=9.5, y=1.02)
    fig.tight_layout()
    save(fig, "footprint")


# ---------------------------------------------------------------------------
# Figure 4 — Hallucination rejection rate (the killer experiment).

def fig_hallucination():
    fig, ax = plt.subplots(figsize=(9.0, 4.0))

    attacks = [
        "Out-of-range\nvalue",
        "Unit\nconfusion",
        "Wrong\ntype",
        "Unknown\nintent",
        "Capability\nescalation",
        "Prompt\ninjection",
    ]
    series = {
        "DCP":     [100, 100, 100, 100, 100, 60],
        "IoT-MCP": [60,   10,  95, 100,   0,  0],
        "Raw MCP": [30,    5,  95, 100,   0,  0],
        "OpenAPI": [70,    5, 100, 100,  50,  5],
    }
    colors = {"DCP": C["dcp"], "IoT-MCP": C["iotmcp"],
              "Raw MCP": C["rawmcp"], "OpenAPI": C["openapi"]}

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

    # Give the figure enough bottom margin for the footnote sitting below the
    # x-axis category labels.
    fig.subplots_adjust(bottom=0.27, top=0.88, left=0.08, right=0.98)
    fig.text(0.5, 0.02,
             "Synthetic data for illustration. Values reflect what each protocol's "
             "schema is expressive enough to reject at the host\n"
             "before any byte reaches the device — they do NOT account for "
             "hand-written application code layered on top.",
             ha="center", va="bottom", fontsize=7.5, color="#666", style="italic")
    save(fig, "hallucination")


# ---------------------------------------------------------------------------
# Figure 5 — End-to-end latency by transport (illustrative).

def fig_latency():
    fig, ax = plt.subplots(figsize=(6.5, 2.6))

    transports = ["DCP\nloopback", "DCP\nUART 115200", "DCP\nMQTT (LAN)", "DCP\nBLE", "IoT-MCP\n[ref]"]
    encode  = [0.3, 0.6,  1.0, 1.0, 3.0]
    wire    = [0.0, 6.0,  3.0, 12.0, 12.0]
    decode  = [0.4, 0.7,  0.8, 0.8, 4.0]
    handler = [0.5, 0.5,  0.5, 0.5, 1.0]
    response_wire = [0.0, 4.0, 2.5, 8.0, 10.0]
    response_decode = [0.3, 0.6, 0.7, 0.7, 3.0]

    layers = [
        ("encode",          encode,          C["dcp_lt"]),
        ("wire out",        wire,            C["dcp"]),
        ("device decode",   decode,          C["rawmcp"]),
        ("handler",         handler,         C["openapi"]),
        ("wire back",       response_wire,   C["matter"]),
        ("host decode",     response_decode, "#bbbbbb"),
    ]

    bottom = np.zeros(len(transports))
    for name, vals, color in layers:
        ax.bar(transports, vals, bottom=bottom, color=color, label=name,
               edgecolor="white", linewidth=0.4, width=0.55)
        bottom += np.array(vals)

    for i, total in enumerate(bottom):
        ax.text(i, total + 0.8, f"{total:.1f} ms",
                ha="center", va="bottom", fontsize=8, color="#333", fontweight="bold")

    ax.set_ylabel("end-to-end latency (ms)")
    ax.set_ylim(0, max(bottom) * 1.18)
    ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=7,
              bbox_to_anchor=(0.0, 1.15))
    ax.tick_params(axis="x", length=0)
    ax.set_title("End-to-end call latency, broken down (illustrative)",
                 loc="left", pad=18, fontsize=10)
    save(fig, "latency")


# ---------------------------------------------------------------------------
# Driver.

def main():
    print("Generating figures to", HERE)
    fig_architecture()
    fig_wire_format()
    fig_footprint()
    fig_hallucination()
    fig_latency()
    print("Done.")


if __name__ == "__main__":
    main()
