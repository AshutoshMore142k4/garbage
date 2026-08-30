"""OpenAI and Gemini implementations of the same triage-client contract as
`l2_llm_triage.client.TriageClient`: same constructor shape (budget_guard/cache/model/prompt_path),
same public `.triage(bank_line, candidates) -> (TriageResponse, metadata)` return shape, same
prompt (`prompting.py`), same response schema (`models.TriageResponse`), and the same
anti-injection rule -- a `candidate_id` outside the bounded set L1 handed over is treated as a
validation failure, never as a match, exactly like `client.py`'s own `_call_model`.

`client.py` (Anthropic/Claude) is what every doc, the pricing table, and PREREGISTRATION.md were
written against, and is left untouched. These two exist so a whichever-credential-is-available
run is possible without forcing one specific provider on whoever runs the live experiment.

Both pricing tables are a point-in-time snapshot (same caveat as `client.py`'s) -- verify against
the provider's console before a benchmark run whose numbers will be quoted anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from ledgerguard.l2_llm_triage.budget_guard import BudgetGuard
from ledgerguard.l2_llm_triage.cache import ResponseCache
from ledgerguard.l2_llm_triage.client import MAX_ATTEMPTS, MAX_TOKENS, RESPONSE_JSON_SCHEMA
from ledgerguard.l2_llm_triage.prompting import build_user_content, sha256
from ledgerguard.models import TriageResponse

# Gemini's structured-output schema is an OpenAPI 3.0 subset: it has no `type: [x, "null"]`
# union syntax, so `candidate_id`'s nullability has to be expressed as `nullable: true` instead
# of the `RESPONSE_JSON_SCHEMA` used by Anthropic/OpenAI (both of which accept a type array).
GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidate_id": {"type": "string", "nullable": True},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["candidate_id", "confidence", "evidence"],
}


def _validate(data: dict, candidate_ids: set[str]) -> Optional[TriageResponse]:
    try:
        parsed = TriageResponse.model_validate(data)
    except ValidationError:
        return None
    if parsed.candidate_id is not None and parsed.candidate_id not in candidate_ids:
        # Same harmless-by-construction treatment as client.py: the model named something
        # outside the bounded set it was given -- never trust it as a match.
        return None
    return parsed


class OpenAITriageClient:
    """Requires `pip install openai`. Uses Chat Completions' structured-output mode (JSON
    Schema, strict) so the response shape is enforced by the provider before it reaches here.
    """

    PRICE_PER_MTOK_USD = {"input": 0.15, "output": 0.60}  # gpt-4o-mini

    def __init__(
        self,
        client: Any,
        budget_guard: BudgetGuard,
        cache: Optional[ResponseCache] = None,
        model: str = "gpt-4o-mini",
        prompt_path: Path = Path("prompts/residual_triage_v1.md"),
    ) -> None:
        self._client = client
        self._budget_guard = budget_guard
        self._cache = cache or ResponseCache()
        self._model = model
        self._system_prompt = Path(prompt_path).read_text(encoding="utf-8")
        self._prompt_hash = sha256(self._system_prompt)[:16]

    @property
    def prompt_hash(self) -> str:
        return self._prompt_hash

    def _cache_key(self, user_content: str) -> str:
        return sha256(f"{self._prompt_hash}:{self._model}:{user_content}")

    def _estimate_worst_case_cost(self, system_prompt: str, user_content: str) -> float:
        # No local tokenizer dependency: a 4-chars-per-token heuristic on the input side, plus
        # the real cap (MAX_TOKENS) on the output side, priced at the more expensive direction.
        approx_input_tokens = (len(system_prompt) + len(user_content)) / 4
        return (
            approx_input_tokens / 1_000_000 * self.PRICE_PER_MTOK_USD["input"]
            + MAX_TOKENS / 1_000_000 * self.PRICE_PER_MTOK_USD["output"]
        )

    def _call_model(self, user_content: str, candidate_ids: set[str]) -> tuple[Optional[TriageResponse], float]:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "triage_response", "schema": RESPONSE_JSON_SCHEMA, "strict": True},
            },
        )
        usage = response.usage
        usd_cost = (
            usage.prompt_tokens / 1_000_000 * self.PRICE_PER_MTOK_USD["input"]
            + usage.completion_tokens / 1_000_000 * self.PRICE_PER_MTOK_USD["output"]
        )

        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            return None, usd_cost
        text = choice.message.content
        if not text:
            return None, usd_cost

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None, usd_cost
        return _validate(data, candidate_ids), usd_cost

    def triage(self, bank_line: dict, candidates: list[dict]) -> tuple[TriageResponse, dict]:
        candidate_ids = {c["payment_id"] for c in candidates}
        user_content = build_user_content(bank_line, candidates)
        cache_key = self._cache_key(user_content)

        cached = self._cache.get(cache_key)
        if cached is not None:
            response = TriageResponse.model_validate(cached["response"])
            return response, {
                "model": self._model,
                "prompt_hash": self._prompt_hash,
                "from_cache": True,
                "usd_cost": 0.0,
                "abstained": cached["abstained"],
            }

        total_cost = 0.0
        parsed: Optional[TriageResponse] = None
        for _attempt in range(MAX_ATTEMPTS):
            estimate = self._estimate_worst_case_cost(self._system_prompt, user_content)
            self._budget_guard.check(estimate)
            parsed, cost = self._call_model(user_content, candidate_ids)
            total_cost += cost
            self._budget_guard.charge(cost)
            if parsed is not None:
                break

        abstained = parsed is None
        result = parsed or TriageResponse(
            candidate_id=None, confidence=0.0, evidence=["schema validation failed after retry"]
        )
        self._cache.put(cache_key, {"response": result.model_dump(), "abstained": abstained})
        return result, {
            "model": self._model,
            "prompt_hash": self._prompt_hash,
            "from_cache": False,
            "usd_cost": total_cost,
            "abstained": abstained,
        }


class GeminiTriageClient:
    """Requires `pip install google-generativeai`. Uses Gemini's `response_schema` structured
    output (an OpenAPI 3.0 subset -- see `GEMINI_RESPONSE_SCHEMA` above for why it differs from
    `RESPONSE_JSON_SCHEMA`).
    """

    PRICE_PER_MTOK_USD = {"input": 0.10, "output": 0.40}  # gemini flash-lite class pricing estimate

    def __init__(
        self,
        genai_module: Any,
        budget_guard: BudgetGuard,
        cache: Optional[ResponseCache] = None,
        model: str = "gemini-3.5-flash-lite",
        prompt_path: Path = Path("prompts/residual_triage_v1.md"),
    ) -> None:
        self._budget_guard = budget_guard
        self._cache = cache or ResponseCache()
        self._model_name = model
        self._system_prompt = Path(prompt_path).read_text(encoding="utf-8")
        self._prompt_hash = sha256(self._system_prompt)[:16]
        self._genai = genai_module
        self._model = genai_module.GenerativeModel(model, system_instruction=self._system_prompt)

    @property
    def prompt_hash(self) -> str:
        return self._prompt_hash

    def _cache_key(self, user_content: str) -> str:
        return sha256(f"{self._prompt_hash}:{self._model_name}:{user_content}")

    def _estimate_worst_case_cost(self, system_prompt: str, user_content: str) -> float:
        approx_input_tokens = (len(system_prompt) + len(user_content)) / 4
        return (
            approx_input_tokens / 1_000_000 * self.PRICE_PER_MTOK_USD["input"]
            + MAX_TOKENS / 1_000_000 * self.PRICE_PER_MTOK_USD["output"]
        )

    def _call_model(self, user_content: str, candidate_ids: set[str]) -> tuple[Optional[TriageResponse], float]:
        response = self._model.generate_content(
            user_content,
            generation_config=self._genai.types.GenerationConfig(
                max_output_tokens=MAX_TOKENS,
                response_mime_type="application/json",
                response_schema=GEMINI_RESPONSE_SCHEMA,
            ),
        )
        usage = response.usage_metadata
        usd_cost = (
            usage.prompt_token_count / 1_000_000 * self.PRICE_PER_MTOK_USD["input"]
            + usage.candidates_token_count / 1_000_000 * self.PRICE_PER_MTOK_USD["output"]
        )

        if not response.candidates or response.candidates[0].finish_reason not in (1, "STOP"):
            return None, usd_cost  # SAFETY / RECITATION / MAX_TOKENS / etc. -- never guess

        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, ValueError):
            return None, usd_cost
        return _validate(data, candidate_ids), usd_cost

    def triage(self, bank_line: dict, candidates: list[dict]) -> tuple[TriageResponse, dict]:
        candidate_ids = {c["payment_id"] for c in candidates}
        user_content = build_user_content(bank_line, candidates)
        cache_key = self._cache_key(user_content)

        cached = self._cache.get(cache_key)
        if cached is not None:
            response = TriageResponse.model_validate(cached["response"])
            return response, {
                "model": self._model_name,
                "prompt_hash": self._prompt_hash,
                "from_cache": True,
                "usd_cost": 0.0,
                "abstained": cached["abstained"],
            }

        total_cost = 0.0
        parsed: Optional[TriageResponse] = None
        for _attempt in range(MAX_ATTEMPTS):
            estimate = self._estimate_worst_case_cost(self._system_prompt, user_content)
            self._budget_guard.check(estimate)
            parsed, cost = self._call_model(user_content, candidate_ids)
            total_cost += cost
            self._budget_guard.charge(cost)
            if parsed is not None:
                break

        abstained = parsed is None
        result = parsed or TriageResponse(
            candidate_id=None, confidence=0.0, evidence=["schema validation failed after retry"]
        )
        self._cache.put(cache_key, {"response": result.model_dump(), "abstained": abstained})
        return result, {
            "model": self._model_name,
            "prompt_hash": self._prompt_hash,
            "from_cache": False,
            "usd_cost": total_cost,
            "abstained": abstained,
        }
