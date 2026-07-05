# **Finance Data Pipeline**  
A modular Python pipeline that fetches financial and macro‑economic data from multiple public sources (Yahoo Finance, FRED, ECB, etc.) and writes normalized time‑series metrics into TimescaleDB.  The system supports both base metrics (direct API fetches) and composite metrics (Python expressions computed from other metrics).

The goal is a **deterministic, reliable, and extensible ingestion layer** for dashboards such as Grafana.

---

## Configuration
There are two files involve in configuration:
- [config.yaml](config.yaml) contains the non-sensitive configuration data
- [.env](.env.example) contains environment variable definitions for secrets. You can also choose to store these variables in your environment.

### Environment variables and secrets
As secrets are not to be shared, the repo only has an example .env file, which you can use as example. 

Supported entries
- `FRED_API_KEY`: the API key for FRED (mandatory). 
- `YAHOO_API_KEY`: the API key for Yahoo (optional).
- `TIMESCALEDB_HOST`: the TimescaleDB host e.g. `localhost`.
- `TIMESCALEDB_DB`: the database for Timescale, e.g. `finance`.
- `TIMESCALEDB_USER`: the user id
- `TIMESCALEDB_PASSWORD`: the corresponding password
- `TIMESCALEDB_SSL_MODE`: the SSL mode in PostgreSQL format. Default is `verify-full`. You can use `disable` to use plain TCP instead of TLS, or `require` to use TLS but not validate the certs. You can also use `verify-ca` to verify the CA cert but not the hostname. 
- `TIMESCALEDB_SSL_ROOT_CERT`: the location of the CA certificate to be used. If omitted, the standard CA cert storage will be used. 

Everything but the secrets (API keys, credentials) can also be specified in the Environment configuration section of `config.yaml`.

### Environment Configuration

This section contains settings that determine the technical setup and operation, such as like logging level, paths, and TimescaleDB settings.

If you don't consider the `url`, `db`, `ssl_mode` or `ssl_root_cert` sensitive, you can also store these in `config.yaml`, under the `environment`-`timescaledb`.
If settings are in both locations, the one in `config.yaml` is taken.

### Business Configuration

This section contains the definitions of `providers` (providing the series), `assets` (series definitions) and `composites` (calculations on series), and supporting structures (`field_sets`). Composites have been disabled for the first release.

#### Providers
Three providers are currently supported: Yahoo (chart API), Fred and ECB. 
The config looks as follows:
```
business:
  providers:
    yahoo:
      timeout: 10s
      timezone: UTC
      constraints:
        history_limits:
          default: 60d
          1m: 7d
          60m: 730d
          1d: null
```
Read this as follows: for the provider Yahoo, the request timeout is 10 seconds, and the default timezone is UTC.
It has a default of 60 days for the history limit, but for one minute it is 7 days, and for 1 day there is no limit

#### Series templates

We distinguish assets and series. Asset is a specific financial instrument, such as a share of a company, an currency exchange rate or an published interest rate.
Every asset can have one or more (usually max 2) series, a longer term one (interval 1 day or more) and a short term one with interval less than a day (intraday).

You define as them follows:

business:
  series_templates:
    intraday_candle:
      interval: 5m
      series_type: candle
      retention: short_lived
      bootstrap_history: 30d

This means we define a re-usable series template named `intraday_candle` which defines an interval of 5 minutes, a candle type [`open`, `high`, `low`, `close`, `volume`], and stored in the short lived table. On first fetch, it will try and fetch 30 days of history. 
For series type, you can also use `value`. In that case, only the `close` field will be populated. This is useful for instruments that don't have the full candle like the ECB USD/EUR rate, and the FRED interest rates. All except the interval can be defaulted. For series type, the default is `candle`. The other two have defaults that depend on the interval. If the interval is less than a day, the default retention is `short_lived`, else `long_lived`. For bootstrap_history it's `30d` (30 days) and `10y` (10 years), respectively.

The `interval` amd `bootstrap_history` are durations. They are specified by a number and a letter, where allowed values are `m` (minutes), `h` (hours)or `d` (days) `w` (weeks) or `y` (years of 365.25 days).

#### Assets

The asset entries specify the assets in scope along with their series.

Example:

```
business:
  assets:
    gold:
      provider:
        name: yahoo
        code: GC=F
      symbol: GOLD
      tags:
        instrument: commodity
        exchange: COMMODITY
        region: GLOBAL
        currency: USD
        unit: troy_ounce
      series:
        intraday: intraday_candle
        daily: daily_candle
```

In this example, `gold` is the asset key, which must be unique and should not be changed after it has been ingested into the database. 
The `provider` section specifies which provider to use  and which provider code to use for fetching. The symbol here is `GOLD`. You can also omit it, and then the key (in this case `gold`) will be used instead. The tags are metadata that you can use for querying. The series section defines the series, using the series templates as defined earlier. You can also make this a section with the same entries as the template instead of a reference. 



#### Composites

Composites have been disabled for V1. They will be re-introduced later.

Intent is to define composite data using base data or even other composites. They also have a unique user defined identifier, and always have an `expression` referring to the other identifiers. For single value series, you do not need to use the field name, for multi valued ones you do. so `fred_10y_nominal - fred_10y_breakeven` is correct assuming both
identifiers exist in asset definitions. For multi-value assets, use `asset.field` as in e.g. `gold_daily.high - gold_daily.low`. Composites can also have InfluxDB `tags` and `timeseries` (daily or intraday). You can use arithmetical functions like `+`, `-`, `*`, `/`, `min`, `max`, `math.sqrt` and others. Dependencies are taken into account, and cycles will be rejected. 


---

## Project Structure

The repository layout is as follows
```
db/ 
    # the SQL scripts to create the database and its tables
ops/
    # system test scripts
scripts/
    # bash scripts used by makefile
src/
  finance/
    common/
        # shared logic
    composites/
        # dependency detection and evaluator
    config/
        # loader for config.yaml and .env, flattening structure
    fetch/
        # fetching data from the providers and transforming to standard format
    registry/
        # the asset and series registry
    state/
        # capturing last values and timestamps per asset as well as a write ahead logger (WAL)
    timeseries/
        # reading from and writing to TimescaleDB
    main_utils.py    # utilities for main
    main.py          # the main application
systemd/
    # definitions to use the application as a timed service
tests/
    # unit tests for finance and tools
tools/
    # development tools (adding license header)
config.yaml          # configuration (e.g. assets and composites), see above
.env.example         # example content for .env (secrets)
.env.acc             # environment settings for acceptance deployment
.env.prod            # environment settings for production deployment
LICENSE              # the license file
makefile             # testing/building/deploying the application
pyproject.toml       # project definition
pytest.ini           # pytest config
README.md            # this file
ruff.toml            # ruff (static analysis) config
```

---

## **Installation**

A makefile is provided. `make help` will provide the targets

Define `.env.prod` and `.env.acc` for production and acceptance environments. Examples are provided. Contents are simple:
```
ENV_ROOT=/home/pi/acc/finance
ENV_USER=pi
```

Makefile will use these as the target for `make acceptance` and `make production`

It will copy `.env.example` to `.env` in the target. Fill in API keys and secrets, and delete or comment out unwanted variables.

edit `config.yaml` and get it to fetch/store the assets you want. 

---

## **Running the Pipeline**

```bash
python -m finance
```

You can schedule it via cron, systemd timers, or any scheduler.

---

## **Running Tests**

The project uses **pytest**.   [Current page]
Run all tests:

```bash
pytest
```

Run a specific subsystem:

```bash
pytest tests/config
```

Ensure the package is on the Python path if needed:

```bash
PYTHONPATH=. pytest
```

---

## **Contributing**

When extending the pipeline:
- Keep the code clean.  
- Favor clarity over cleverness.  
- Ensure over 99% code coverage  
- Keep composite expressions deterministic  
- Avoid unnecessary API calls  
  
---

## **License**

Apache License 2.0.  
See `LICENSE` for details.