"""Empirical version of bench_hallucination.py — consumes the corpus
of tool calls actually produced by real LLMs (captured by
tools/gen_llm_corpus.py and stored in tools/llm_corpus.json), and
measures the schema-layer rejection rate of each protocol over that
real corpus.

Methodology, in one sentence: take every tool call the LLM emitted in
response to an adversarial prompt, feed it to each of the four
protocols' host-side validators, and compute the fraction that each
protocol refuses before any byte reaches the device.

We aggregate across all models that returned parseable tool calls;
per-model breakdowns are also written for transparency. Models whose
tool-calling output we could not parse for any prompt (e.g. small
models that don't natively support OpenAI function-calling) are
listed but excluded from the rejection-rate aggregation, since
"the LLM refused to emit a tool call" is not a protocol-layer event.

Output: docs/paper/figures/hallucination_data.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bench_hallucination import PROTOCOLS, CORPUS  # noqa: E402,F401

CORPUS_PATH = ROOT / "tools" / "llm_corpus.json"
OUT_PATH    = ROOT / "docs" / "paper" / "figures" / "hallucination_data.json"


def collect_parsed(corpus: dict[str, list[dict]]) -> dict[str, list[tuple[str, dict]]]:
    parsed: dict[str, list[tuple[str, dict]]] = {}
    for cat, entries in corpus.items():
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
    return parsed


def measure(parsed: dict[str, list[tuple[str, dict]]]) -> dict:
    """Run all PROTOCOLS over the parsed calls, return summary dict."""
    rejection_pct = {p: [] for p in PROTOCOLS}
    raw_counts = {p: {} for p in PROTOCOLS}
    categories = list(parsed.keys())
    for cat in categories:
        n = len(parsed[cat])
        for proto_name, validate in PROTOCOLS.items():
            if n == 0:
                pct, rej = 0, 0
            else:
                rej = sum(1 for (i, p) in parsed[cat] if validate(i, p))
                pct = round(100.0 * rej / n)
            rejection_pct[proto_name].append(pct)
            raw_counts[proto_name][cat] = {
                "rejected": rej, "accepted": n - rej, "total": n,
            }
    return {
        "categories":      categories,
        "n_per_category":  {c: len(parsed[c]) for c in categories},
        "rejection_pct":   rejection_pct,
        "raw_counts":      raw_counts,
    }


def main() -> None:
    if not CORPUS_PATH.exists():
        raise SystemExit(
            f"{CORPUS_PATH} missing — run tools/gen_llm_corpus.py first.")
    blob = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    # Handle both single-model (legacy) and multi-model corpus shapes.
    if "by_model" in blob:
        by_model_raw = blob["by_model"]
    else:
        # Legacy single-model JSON had `corpus` and `model` at top level.
        by_model_raw = {blob.get("model", "unknown"): blob["corpus"]}

    # Per-model parsed + measurements (always recorded, even if some
    # models had zero parseable calls).
    per_model = {}
    usable_models = []
    for model, raw_corpus in by_model_raw.items():
        parsed = collect_parsed(raw_corpus)
        total_parsed = sum(len(v) for v in parsed.values())
        per_model[model] = {
            "total_parsed": total_parsed,
            "n_per_category": {c: len(v) for c, v in parsed.items()},
        }
        if total_parsed > 0:
            per_model[model]["measurements"] = measure(parsed)
            usable_models.append(model)
        else:
            per_model[model]["measurements"] = None

    # Aggregate across usable models — union of all parsed calls.
    agg_parsed: dict[str, list[tuple[str, dict]]] = {}
    first = True
    for model in usable_models:
        p = collect_parsed(by_model_raw[model])
        if first:
            for c, v in p.items():
                agg_parsed[c] = list(v)
            first = False
        else:
            for c, v in p.items():
                agg_parsed[c].extend(v)
    aggregate = measure(agg_parsed)

    result = {
        "source":           "llm_corpus.json",
        "models":           list(by_model_raw.keys()),
        "usable_models":    usable_models,
        "protocols":        list(PROTOCOLS.keys()),
        # Top-level fields below are the AGGREGATE numbers — what the
        # figure plots. Per-model breakdown is in `per_model`.
        "categories":       aggregate["categories"],
        "n_per_category":   aggregate["n_per_category"],
        "rejection_pct":    aggregate["rejection_pct"],
        "raw_counts":       aggregate["raw_counts"],
        "per_model":        per_model,
    }

    print(f"Models in corpus: {len(by_model_raw)}; usable (>=1 parsed call): {len(usable_models)}")
    for m in by_model_raw:
        tag = "[OK]" if m in usable_models else "[--] excluded (no parsed calls)"
        print(f"  {tag}  {m}  ({per_model[m]['total_parsed']} parsed)")

    print(f"\nAggregate ({sum(aggregate['n_per_category'].values())} parsed calls):")
    print("Category".ljust(24) + "n   " + "  ".join(p.ljust(7) for p in PROTOCOLS))
    print("-" * 60)
    for cat in aggregate["categories"]:
        n = aggregate["n_per_category"][cat]
        row = f"{cat:24}{n:<4}"
        for p in PROTOCOLS:
            row += f"{aggregate['rejection_pct'][p][aggregate['categories'].index(cat)]:3d}%   ".ljust(9)
        print(row)

    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
