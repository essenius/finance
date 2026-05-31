from unittest.mock import Mock, patch

from finance.timeseries.influx import InfluxBackend


def test_influx_backend_read_v2_flux():
    secrets = {
        "url": "https://example.com",
        "org": "myorg",
        "token": "abc123",
        "ssl_verify": "false",
    }

    backend = InfluxBackend(secrets)

    mock_response = Mock()
    mock_response.json.return_value = {"results": "ok"}
    mock_response.raise_for_status.return_value = None

    with patch.object(backend.session, "post", return_value=mock_response) as mock_post:
        result = backend.read("finance_intraday", "eurusd", 1000, 2000)

    assert result["ok"] is True
    assert result["data"] == {"results": "ok"}

    # Verify Flux query was sent
    args, kwargs = mock_post.call_args
    assert "from(bucket: \"finance_intraday\")" in kwargs["data"]
    assert "eurusd" in kwargs["data"]


def test_influx_backend_read_v1_influxql():
    secrets = {
        "url": "https://example.com",
        "db": "finance",
        "ssl_verify": "false",
    }

    backend = InfluxBackend(secrets)

    mock_response = Mock()
    mock_response.json.return_value = {"series": []}
    mock_response.raise_for_status.return_value = None

    with patch.object(backend.session, "get", return_value=mock_response) as mock_get:
        result = backend.read(None, "eurusd", 1000, 2000)

    assert result["ok"] is True
    assert result["data"] == {"series": []}

    args, kwargs = mock_get.call_args
    assert "SELECT * FROM eurusd" in kwargs["params"]["q"]


def test_influx_backend_read_error():
    secrets = {
        "url": "https://example.com",
        "org": "myorg",
        "token": "abc123",
        "ssl_verify": "false",
    }

    backend = InfluxBackend(secrets)

    with patch.object(backend.session, "post", side_effect=Exception("boom")):
        result = backend.read("bucket", "eurusd", 0, 10)

    assert result["ok"] is False
    assert "boom" in result["error"]
