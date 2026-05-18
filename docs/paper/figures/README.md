# Paper figures

All paper figures are generated programmatically by `make_figures.py`.
This keeps them under version control as source, reproducible, and easy to
update when the measurement numbers move from synthetic to measured.

## Regenerate

```powershell
python -m pip install matplotlib numpy   # only deps
python make_figures.py
```

Outputs both PDF (for the LaTeX `\includegraphics`) and PNG (for the
README / web preview) into this directory.

## What each figure shows

| File | Figure | Purpose |
|---|---|---|
| `arch.pdf` | Fig. 1 | High-level architecture, expanded Bridge components |
| `wire_format.pdf` | Fig. 2 | DCP frame byte layout + wire-size vs other protocols |
| `footprint.pdf` | Fig. 3 | Flash & RAM comparison: DCP vs IoT-MCP vs raw MCP vs Matter |
| `hallucination.pdf` | Fig. 4 | What % of malformed/adversarial LLM calls each protocol catches |
| `latency.pdf` | Fig. 5 | End-to-end latency broken down per transport |

## What's synthetic vs measured

**As of paper v0.1**: every numeric value in figures 3–5 is illustrative.
The architecture diagram and the wire-format byte counts (Fig. 1, top half
of Fig. 2) are exact.

Once the hardware campaign is complete:

- Fig. 3 — replace DCP "target" bars with measured values across
  ESP32, ESP32-C3, nRF52840.
- Fig. 4 — replace the synthetic rejection-rate values with measured
  results from running 1000 LLM-generated adversarial calls against each
  baseline; will need to define the attack-generation procedure.
- Fig. 5 — replace with median + IQR from 1000 round-trips per transport.

Edit `make_figures.py` directly — each figure is one function. Re-run.
Don't hand-edit the PDFs.
