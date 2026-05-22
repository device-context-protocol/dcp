# DCP paper draft

Position-paper-style preprint, single-column `article` class, ~9–10 pages
compiled. Targeted at arXiv (cs.NI / cs.DC), with the option to revise
downward for a workshop submission (HotNets / HotMobile / SafeAI) or
upward with empirical evaluation for IoTDI / SenSys / MobiSys.

## Build

You need a working TeX distribution. The cleanest cross-platform option is
[Tectonic](https://tectonic-typesetting.github.io/) — single static binary,
fetches packages on demand:

```powershell
tectonic main.tex
```

Or with TeX Live / MiKTeX:

```powershell
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

Output: `main.pdf`.

## Submit to arXiv

```powershell
# Builds figures + paper + arXiv-ready tarball
.\build-arxiv.ps1
```

Outputs `dcp-arxiv-vX.Y.Z.tar.gz` (~80 KB). Upload it at
[arxiv.org/submit](https://arxiv.org/submit):

- **Primary category:** `cs.NI` (Networking and Internet Architecture)
- **Secondary (optional):** `cs.DC` (Distributed Computing) and/or `cs.LG`
- **License:** arXiv non-exclusive license
- **Title:** match the LaTeX `\title{}`
- **Abstract:** copy from LaTeX `\begin{abstract}`

arXiv will run pdflatex itself; the tarball already includes the precompiled
`main.bbl` so the bibliography resolves on first pass.

The tarball is `.gitignored` — regenerate before each upload.

## Before submitting to arXiv

1. **Authors.** Replace `DeepLethe` and the placeholder email. arXiv lets
   you list affiliations per-author.
2. **Repo URL.** Currently a footnote placeholder
   (`github.com/device-context-protocol`). Either point to the real public
   repo at submission time, or remove the footnote until the org goes live.
3. **`Anonymous` in `refs.bib` for IoT-MCP.** Replace with real authors
   from the actual arXiv listing once you've fetched it.
4. **Measurements.** The paper is honest about *not* having measured
   footprint or latency. Once the hardware campaign is done, add a §6
   Evaluation and drop the explicit "we do not claim" language from §7.
5. **Figure.** `Figure 1` is a simple TikZ architecture diagram. If you
   prefer a polished SVG/PDF figure, export from draw.io / Figma and
   replace the `tikzpicture` with `\includegraphics`.
6. **arXiv class.** arXiv accepts plain `article`; no class change needed.
   If you later target a venue, swap the documentclass to that venue's
   style (e.g.\ `acmart`, `IEEEtran`).

## Length

If the compiled PDF runs long, the easiest trim points are:

- §2.3 (existing IoT protocols) — already concise; can be cut to one paragraph
- §5 (Related Work) — IoT-MCP is essential; the other three can be a
  single paragraph if needed
- §7 (Discussion) — the "what this paper does not prove" disclosure can
  shrink once measurement is done

If it runs short, the easiest expansion points:

- §3.4 (Safety model) — concrete examples of LLM-hallucinated calls and
  what each layer catches
- §4.2 (Firmware) — a code excerpt showing a handler implementation
- §7.3 (Open questions) — more depth on each

## Suggested next steps after circulating the draft

1. **Post to arXiv** (1–2 weeks): claims priority, gets discovered.
2. **Hardware measurement campaign** (4–8 weeks): flash/RAM on 3 MCUs,
   end-to-end latency, hallucination-rejection rate vs baselines.
3. **Full evaluation paper**: target IoTDI 2027 or SenSys 2026 with the
   measurement results.

## Files

- `main.tex` — the paper
- `refs.bib` — BibTeX bibliography
- `main.pdf` — generated (gitignored)
