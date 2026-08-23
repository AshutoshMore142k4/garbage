import pytest
from pydantic import ValidationError

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


def test_missing_required_secret_raises_clearly(monkeypatch):
    for key, value in REQUIRED_SECRETS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    assert "llm_api_key" in str(excinfo.value)
