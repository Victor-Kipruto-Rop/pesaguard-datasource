import pytest

from src import worker


@pytest.fixture
def retry_settings(monkeypatch):
    monkeypatch.setattr(worker.settings, "worker_retry_seconds", 30)
    monkeypatch.setattr(worker.settings, "worker_retry_max_seconds", 120)


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [(1, 30), (2, 60), (3, 120), (4, 120), (500, 120)],
)
def test_retry_delay_grows_exponentially_and_is_capped(monkeypatch, retry_settings, attempts, expected):
    monkeypatch.setattr(worker.random, "uniform", lambda lower, upper: upper)
    assert worker._retry_delay_seconds(attempts) == expected


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [(1, 15), (2, 30), (3, 60), (4, 60)],
)
def test_retry_delay_uses_equal_jitter(monkeypatch, retry_settings, attempts, expected):
    monkeypatch.setattr(worker.random, "uniform", lambda lower, upper: lower)
    assert worker._retry_delay_seconds(attempts) == expected


def test_retry_delay_never_returns_zero_or_negative(monkeypatch):
    monkeypatch.setattr(worker.settings, "worker_retry_seconds", 0)
    monkeypatch.setattr(worker.settings, "worker_retry_max_seconds", 0)
    monkeypatch.setattr(worker.random, "uniform", lambda lower, upper: lower)
    assert worker._retry_delay_seconds(0) == 1
