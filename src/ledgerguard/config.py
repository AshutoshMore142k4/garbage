"""Typed settings loaded from the environment (and an optional .env file).

Field names map to the env vars documented in .env.example (case-insensitive). All secrets
default to "" rather than being required: a hackathon judge running `make api`/`make close`
with no credentials at all must get the free fallback, not a ValidationError, and a caller who
only has one of the three LLM provider keys shouldn't have to fabricate the other two just to
construct Settings. `l2_llm_triage/factory.py` is what actually decides which (if any) LLM
provider is usable, based on which of `llm_api_key` (Anthropic), `openai_api_key`, or
`gemini_api_key` is non-empty; `llm_provider` optionally forces a specific one when more than
one key is set.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    llm_provider: str = ""  # "anthropic" | "openai" | "gemini" -- forces a choice; blank = auto
    llm_api_key: str = ""  # Anthropic
    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Model IDs drift fast across all three providers -- overridable here rather than requiring
    # a code change every time a provider deprecates one.
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-3.5-flash-lite"

    max_spend_usd: float = 2.0
    seed: int = 42
    confidence_threshold: float = 0.94
    authority_limit_paise: int = 10_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
