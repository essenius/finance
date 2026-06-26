# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_influx_read.py

"""
TODO delete
@pytest.mark.parametrize(
    "backend_fixture, asc, expected_method, expected_query_check",
    [
        # v1 first
        (
            "backend_v1",
            True,
            "get",
            "ORDER BY time ASC LIMIT 1",
        ),
        # v1 last
        (
            "backend_v1",
            False,
            "get",
            "ORDER BY time DESC LIMIT 1",
        ),
        # v2 first
        (
            "backend_v2",
            True,
            "post",
            'sort(columns: ["_time"], desc: false)',
        ),
        # v2 last
        (
            "backend_v2",
            False,
            "post",
            'sort(columns: ["_time"], desc: true)',
        ),
    ],
)
def test_read_one_unified(request, backend_fixture, asc, expected_method, expected_query_check):
    backend = request.getfixturevalue(backend_fixture)
    session = backend.session

    # --- Mock backend responses ---
    if backend_fixture == "backend_v1":
        session.get.return_value = Mock(
            raise_for_status=lambda: None,
            json=lambda: {
                "results": [
                    {
                        "series": [
                            {
                                "columns": ["time", "value"],
                                "values": [["2024-01-01T00:00:00Z", 10]],
                            }
                        ]
                    }
                ]
            },
        )
    else:
        session.post.return_value = Mock(
            raise_for_status=lambda: None,
            json=lambda: {
                "tables": [
                    {
                        "records": [
                            {
                                "_measurement": "m",
                                "_time": "2024-01-01T00:00:00Z",
                                "_field": "value",
                                "_value": 10,
                            }
                        ]
                    }
                ]
            },
        )

    # --- Execute ---
    result = backend.read_one("bucket", "m", asc=asc)

    # --- Unified result assertions ---
    assert result.ok
    assert result.payload.fields == {"value": 10}
    assert result.payload.timestamp == 1704067200

    # --- Query verification ---
    if expected_method == "get":
        session.get.assert_called_once()
        args, kwargs = session.get.call_args
        q = kwargs["params"]["q"]
        assert expected_query_check in q
    else:
        session.post.assert_called_once()
        args, kwargs = session.post.call_args
        body = kwargs["data"]
        assert expected_query_check in body


def test_read_v2_exception(backend_v2):
    session = backend_v2.session
    session.post.side_effect = Exception("fail")

    result = backend_v2.read_first("bucket", "m")
    assert not result.ok
    assert "Influx read failed" in result.reason


def test_read_v1_exception(backend):
    session = backend.session
    session.get.side_effect = Exception("fail")

    result = backend.read_last("bucket", "m")
    assert not result.ok
    assert "Influx read failed" in result.reason


def test_read_v2_url_and_headers(backend_v2):
    session = backend_v2.session
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"tables": []}
    session.post.return_value = fake_response

    backend_v2.read_first("bucket", "m")

    url = session.post.call_args.args[0]
    assert url.endswith("/query")
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Token 123"
"""
