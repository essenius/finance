import pytest

from finance.config.loader import load_env_secrets


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Remove all Influx-related variables. They can bleed in
    # from the real environment or the real .env file
    for var in [
        "INFLUX_URL",
        "INFLUX_SSL_VERIFY",
        "INFLUX_SSL_CERT",
        "INFLUX_DB",
        "INFLUX_ORG",
        "INFLUX_TOKEN",
        "INFLUX_READ_TOKEN",
        "INFLUX_WRITE_TOKEN",
        "INFLUX_USER",
        "INFLUX_PASSWORD",
        "FRED_API_KEY",
        "YAHOO_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_load_env_secrets_influx1(monkeypatch, tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\nFRED_API_KEY=abc\n")

    monkeypatch.setenv("INFLUX_USER", "u")
    monkeypatch.setenv("INFLUX_PASSWORD", "p")
    monkeypatch.setenv("YAHOO_API_KEY", "yahoo123")
    monkeypatch.setenv("FRED_API_KEY", "overwritten")

    secrets = unwrap(load_env_secrets(env))["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["db"] == "db"
    assert secrets["influx"]["user"] == "u"
    assert secrets["influx"]["password"] == "p"

    assert secrets["api_keys"]["fred"] == "abc"
    assert secrets["api_keys"]["yahoo"] == "yahoo123"


def test_load_env_secrets_influx2_one_token(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_TOKEN=tok123\n")

    secrets = unwrap(load_env_secrets(env))["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["write-token"] == "tok123"
    assert secrets["influx"]["read-token"] == "tok123"


def test_load_env_secrets_influx2_two_tokens(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_READ_TOKEN=tok123\nINFLUX_WRITE_TOKEN=123tok\n")

    secrets = unwrap(load_env_secrets(env))["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["write-token"] == "123tok"
    assert secrets["influx"]["read-token"] == "tok123"


def test_load_env_secrets_influx2_fallback_token(tmp_path, unwrap):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_READ_TOKEN=tok123\nINFLUX_TOKEN=123tok\n")

    secrets = unwrap(load_env_secrets(env))["secrets"]

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["write-token"] == "123tok"
    assert secrets["influx"]["read-token"] == "tok123"


def test_missing_url_fails(tmp_path, assert_error):
    env = tmp_path / ".env"
    env.write_text("")  # no INFLUX_URL

    assert_error(load_env_secrets(env), "requires URL", None)


def test_missing_db_in_influx1(tmp_path, assert_error):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\n")  # no INFLUX_DB

    assert_error(load_env_secrets(env), "InfluxDB 1.x requires database", None)


def test_missing_token_in_influx2(tmp_path, assert_error):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=o\n")  # no token

    assert_error(load_env_secrets(env), "requires INFLUX_WRITE_TOKEN", None)

