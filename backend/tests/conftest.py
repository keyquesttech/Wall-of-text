import pytest

from walloftext.config import Settings
from walloftext.net.nm import FakeNetworkManager


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.hw = "mock"
    s.data_dir = tmp_path / "var"
    s.password_file = tmp_path / "etc" / "passwords.txt"
    s.connect_reply_delay_s = 0
    s.connect_timeout_s = 120
    s.fallback_retry_s = 60
    s.link_lost_s = 300
    return s


@pytest.fixture
def fake_nm():
    return FakeNetworkManager()


class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


@pytest.fixture
def clock():
    return Clock()
