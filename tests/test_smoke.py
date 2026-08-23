import ledgerguard


def test_version_is_string():
    assert isinstance(ledgerguard.__version__, str)
    assert ledgerguard.__version__
