"""Empirical version of bench_hallucination.py — consumes the corpus
of tool calls actually produced by a real LLM (DeepSeek V3 via
SiliconFlow, captured by tools/gen_llm_corpus.py and stored in
tools/llm_corpus.json), and measures the schema-layer rejection rate
of each protocol over that real corpus.

Methodology, in one sentence: take every tool call the LLM emitted in
response to an adversarial prompt, feed it to each of the four
protocols' host-side validators, and compute the fraction that each
protocol refuses before any byte reaches the device.

Output: docs/paper/figures/hallucination_data.json

This replaces the synthetic / hand-crafted corpus that bench_hallu-
cination.py used. The synthetic bench is kept as a separate file for
the supplementary material — the chart in the paper now reflects
real LLM behavior.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Reuse the protocol validators and reference manifest from the
# synthetic bench — we're swapping the corpus, not the rules.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bench_hallucination import PROTOCOLS, CORPUS  # noqa: E402,F401

CORPUS_PATH = ROOT / "tools" / "llm_corpus.json"
OUT_PATH    = ROOT / "docs" / "paper" / "figures" / "hallucination_data.json"


def main() -> None:
    if not CORPUS_PATH.exists():
        raise SystemExit(
            f"{CORPUS_PATH} missing — run tools/gen_llm_corpus.py first.")
    blob = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    raw_corpus: dict[str, list[dict]] = blob["corpus"]

    # For each category, keep only entries where the LLM actually
    # produced a parseable tool call. Prompts where the LLM refused
    # or replied in natural language are excluded — they have no
    # protocol-layer event to measure (rejection happened at the
    # LLM layer, not at the protocol).
    parsed: dict[str, list[tuple[str, dict]]] = {}
    for cat, entries in raw_corpus.items():
        calls: list[tuple[str, dict]] = []
        for e in entries:
            tc = e.get("tool_call")
            if not tc:
                continue
            intent = tc.get("intent")
            params = tc.get("params") or {}
            if isinstance(intent, str):
                calls.append((intent, params))
        parsed[cat] = calls

    result = {
        "source":           "llm_corpus.json",
        "llm_model":        blob.get("model"),
        "categories":       list(parsed.keys()),
        "protocols":        list(PROTOCOLS.keys()),
        "n_per_category":   {c: len(v) for c, v in parsed.items()},
        "rejection_pct":    {},
        "raw_counts":       {},
    }

    print(f"Source: {blob.get('model')} via SiliconFlow\n")
    header = "Category".ljust(24) + "n   " + "  ".join(
        p.ljust(7) for p in PROTOCOLS)
    print(header)
    print("-" * len(header))

    # Initialize per-protocol arrays so iteration order matches
    # `categories` in the JSON.
    for p in PROTOCOLS:
        result["rejection_pct"][p] = []
        result["raw_counts"][p] = {}

    for cat, calls in parsed.items():
        n = len(calls)
        row = f"{cat:24}{n:<4}"
        for proto_name, validate in PROTOCOLS.items():
            if n == 0:
                pct = 0
                rej = 0
            else:
                rej = sum(1 for (i, p) in calls if validate(i, p))
                pct = round(100.0 * rej / n)
            result["rejection_pct"][proto_name].append(pct)
            result["raw_counts"][proto_name][cat] = {
                "rejected": rej, "accepted": n - rej, "total": n,
            }
            row += f"{pct:3d}%   ".ljust(9)
        print(row)

    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
