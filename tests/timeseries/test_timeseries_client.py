from unittest.mock import Mock

from finance.timeseries.client import TimeSeriesClient
from finance.timeseries.errors import TimeSeriesError


def make_client_with_mock_backend():
    """Utility: create a client and replace backend with a mock."""
    secrets = {"url": "x", "org": "y", "token": "z", "ssl_verify": "false"}
    client = TimeSeriesClient(secrets)
    client.backend = Mock()
    return client


# --- WRITE SUCCESS -----------------------------------------------------------

def test_client_write_success():
    client = make_client_with_mock_backend()
    client.backend.write.return_value = {"ok": True, "data": 123}

    result = client.write("bucket", "eurusd", {"close": 1.2345}, {}, 1234567890)

    assert result == {"ok": True, "data": 123}
    client.backend.write.assert_called_once_with(
        "bucket", "eurusd", {"close": 1.2345}, {}, 1234567890
    )


# --- WRITE ERROR → TimeSeriesError ------------------------------------------

def test_client_write_error_wrapped():
    client = make_client_with_mock_backend()
    client.backend.write.side_effect = Exception("backend exploded")

    try:
        client.write("bucket", "eurusd", {"close": 1.2345}, {}, 1234567890)
        raise AssertionError("Expected TimeSeriesError to be raised")
    except TimeSeriesError as e:
        assert "backend exploded" in str(e)
        # ensure exception chaining is suppressed
        assert e.__cause__ is None


# --- READ SUCCESS ------------------------------------------------------------

def test_client_read_success():
    client = make_client_with_mock_backend()
    client.backend.read.return_value = {"ok": True, "rows": []}

    result = client.read("bucket", "eurusd", 1000, 2000)

    assert result == {"ok": True, "rows": []}
    client.backend.read.assert_called_once_with("bucket", "eurusd", 1000, 2000)


# --- READ ERROR → TimeSeriesError -------------------------------------------

def test_client_read_error_wrapped():
    client = make_client_with_mock_backend()
    client.backend.read.side_effect = Exception("read failure")

    try:
        client.read("bucket", "eurusd", 1000, 2000)
        raise AssertionError("Expected TimeSeriesError to be raised")
    except TimeSeriesError as e:
        assert "read failure" in str(e)
        assert e.__cause__ is None
