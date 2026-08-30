from ledgerguard.config import Settings

REQUIRED_SECRETS = {
    "RAZORPAY_KEY_ID": "rzp_test_dummy",
    "RAZORPAY_KEY_SECRET": "dummy_secret",
    "RAZORPAY_WEBHOOK_SECRET": "dummy_webhook_secret",
    "LLM_API_KEY": "dummy_llm_key",
}


def test_loads_with_sane_defaults_when_secrets_present(monkeypatch):
    for key, value in REQUIRED_SECRETS.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.razorpay_key_id == "rzp_test_dummy"
    assert settings.max_spend_usd == 2.0
    assert settings.seed == 42
    assert settings.confidence_threshold == 0.94
    assert settings.authority_limit_paise == 10_000_000


def test_loads_with_no_secrets_at_all(monkeypatch):
    """No secret is required: a judge running `make api`/`make close` with an empty environment
    must get the free fallback, not a crash. Only `l2_llm_triage/factory.py` cares whether any
    of the three LLM keys below is actually non-empty.
    """
    for key in (*REQUIRED_SECRETS, "OPENAI_API_KEY", "GEMINI_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.razorpay_key_id == ""
    assert settings.llm_api_key == ""
    assert settings.openai_api_key == ""
    assert settings.gemini_api_key == ""
    assert settings.llm_provider == ""


def test_llm_provider_keys_are_independently_settable(monkeypatch):
    for key in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")

    settings = Settings(_env_file=None)

    assert settings.gemini_api_key == "dummy_gemini_key"
    assert settings.llm_api_key == ""
