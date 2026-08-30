"""CLI driver for L2 (phases.md Phase 4): reads L1's residual set, runs each record through
a real provider client (Anthropic/OpenAI/Gemini, auto-detected by `factory.build_triage_client`
from whichever credential is set -- see that module) or the free fallback, and reports the
batch's resolution counts and total spend -- printed at the end of the run, per plan.md #19, and
persisted so `/healthz` can report it too (api/app.py reads the same state file).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ledgerguard.l2_llm_triage.budget_guard import BudgetExhaustedError
from ledgerguard.l2_llm_triage.fallback import fallback_triage

SPEND_STATE_PATH = Path("data/cache/l2/last_run_spend.json")


def _fallback_meta(response) -> dict:
    return {
        "model": "fallback_rapidfuzz",
        "prompt_hash": None,
        "from_cache": False,
        "usd_cost": 0.0,
        "abstained": response.candidate_id is None,
    }


def run_l2(
    residual_path: Path,
    out_path: Path,
    triage_client: Optional[Any],
) -> dict[str, Any]:
    """`triage_client=None` routes every record through the free fallback -- used when no LLM
    credentials are available or the caller chooses not to spend at all. Any object exposing
    `.triage(bank_line, candidates) -> (TriageResponse, metadata)` works here -- the real
    Anthropic `TriageClient` and the OpenAI/Gemini clients in `providers.py` all do.
    """
    records = []
    with open(residual_path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))

    resolved = 0
    abstained = 0
    total_spend_usd = 0.0
    budget_exhausted = False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out:
        for record in records:
            bank_line = {
                "credit_paise": record["credit_paise"],
                "value_date": record["value_date"],
                "narration": record["narration"],
            }
            candidates = record["candidates"]

            if triage_client is None or budget_exhausted:
                response = fallback_triage(bank_line["narration"], candidates)
                meta = _fallback_meta(response)
            else:
                try:
                    response, meta = triage_client.triage(bank_line, candidates)
                except BudgetExhaustedError:
                    budget_exhausted = True
                    response = fallback_triage(bank_line["narration"], candidates)
                    meta = _fallback_meta(response)

            total_spend_usd += meta["usd_cost"]
            if response.candidate_id is None:
                abstained += 1
            else:
                resolved += 1

            out.write(
                json.dumps(
                    {
                        "bank_line_id": record["bank_line_id"],
                        "candidate_id": response.candidate_id,
                        "confidence": response.confidence,
                        "evidence": response.evidence,
                        **meta,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    summary = {
        "considered": len(records),
        "resolved": resolved,
        "abstained": abstained,
        "budget_exhausted": budget_exhausted,
        "total_spend_usd": total_spend_usd,
    }

    SPEND_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEND_STATE_PATH.write_text(json.dumps({"last_run_spend_usd": total_spend_usd}, indent=2), encoding="utf-8")

    return summary


def main() -> None:
    import argparse

    from ledgerguard.l2_llm_triage.budget_guard import BudgetGuard

    parser = argparse.ArgumentParser(description="Run L2 residual triage over L1's residual set.")
    parser.add_argument("--residual", type=Path, default=Path("data/raw/residual.jsonl"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--no-llm", action="store_true", help="Use only the free fallback; never call the model.")
    args = parser.parse_args()

    residual_path = args.residual
    if not residual_path.exists():
        residual_path = Path("data/samples/residual.jsonl")
    out_path = args.out or residual_path.with_name("l2_results.jsonl")

    triage_client = None
    if not args.no_llm:
        try:
            from ledgerguard.config import get_settings
            from ledgerguard.l2_llm_triage.factory import build_triage_client

            triage_client, label = build_triage_client(get_settings())
            print(f"L2: {label}" if triage_client is None else f"L2 provider: {label}")
        except Exception as exc:  # missing settings -- degrade to the fallback, don't crash
            print(f"L2: no usable LLM credentials ({exc}); using the free fallback only.")

    summary = run_l2(residual_path, out_path, triage_client)
    print(f"L2 residual triage, {residual_path}:")
    print(f"  considered {summary['considered']}, resolved {summary['resolved']}, abstained {summary['abstained']}")
    print(f"  total spend: ${summary['total_spend_usd']:.4f}")
    if summary["budget_exhausted"]:
        print("  budget exhausted mid-run; remaining records used the free fallback")
    print(f"  results written to {out_path}")


if __name__ == "__main__":
    main()
