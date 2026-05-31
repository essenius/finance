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
        "INFLUX_WRITE_TOKEN",
        "INFLUX_USER",
        "INFLUX_PASSWORD",
        "FRED_API_KEY",
        "YAHOO_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_load_env_secrets_influx1(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_DB=db\nFRED_API_KEY=abc\n")

    monkeypatch.setenv("INFLUX_USER", "u")
    monkeypatch.setenv("INFLUX_PASSWORD", "p")
    monkeypatch.setenv("YAHOO_API_KEY", "yahoo123")
    monkeypatch.setenv("FRED_API_KEY", "overwritten")

    secrets = load_env_secrets(env)

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["db"] == "db"
    assert secrets["influx"]["user"] == "u"
    assert secrets["influx"]["password"] == "p"

    assert secrets["api_keys"]["fred"] == "abc"
    assert secrets["api_keys"]["yahoo"] == "yahoo123"


def test_load_env_secrets_influx2(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=myorg\nINFLUX_TOKEN=tok123\n")

    secrets = load_env_secrets(env)

    assert secrets["influx"]["url"] == "http://x"
    assert secrets["influx"]["org"] == "myorg"
    assert secrets["influx"]["token"] == "tok123"


def test_missing_url_raises(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("")  # no INFLUX_URL

    with pytest.raises(RuntimeError, match="requires URL"):
        load_env_secrets(env)


def test_missing_db_in_influx1(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\n")  # no INFLUX_DB

    with pytest.raises(RuntimeError, match="InfluxDB 1.x requires database"):
        load_env_secrets(env)


def test_missing_token_in_influx2(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("INFLUX_URL=http://x\nINFLUX_ORG=o\n")  # no token

    with pytest.raises(RuntimeError, match="requires INFLUX_WRITE_TOKEN"):
        load_env_secrets(env)

