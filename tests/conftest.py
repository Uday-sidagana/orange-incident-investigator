import pytest


@pytest.fixture(autouse=True)
def disable_real_notifications_in_tests(monkeypatch):
    # A user's configured demo credentials must never turn unit tests into real posts.
    monkeypatch.setenv('LINEAR_ENABLED','false')
    monkeypatch.setenv('SLACK_ENABLED','false')
    monkeypatch.setenv('INVESTIGATION_RUNTIME','simulation')
