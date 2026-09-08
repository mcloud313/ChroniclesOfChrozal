"""Keep process-global authentication limits independent between test scenarios."""
import pytest

@pytest.fixture(autouse=True)
def isolated_auth_buckets():
    from web.auth import buckets
    buckets.clear()
