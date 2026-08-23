"""Typed settings loaded from the environment (and an optional .env file).

Field names map to the env vars documented in .env.example (case-insensitive):
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, LLM_API_KEY are required
secrets with no default -- constructing Settings without them raises a clear ValidationError.
The remaining knobs have the same defaults as .env.example so the system is runnable out of
the box for anything that doesn't need real Razorpay/LLM credentials (e.g. this phase's
in-repo tests, /healthz).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    llm_api_key: str

    max_spend_usd: float = 2.0
    seed: int = 42
    confidence_threshold: float = 0.94
    authority_limit_paise: int = 10_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
