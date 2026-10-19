import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest  # noqa: E402

from apps.api.ratelimit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Keep rate-limit counts isolated between tests."""
    limiter.reset()
    yield
    limiter.reset()
