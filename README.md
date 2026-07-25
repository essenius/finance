# **Finance Data Pipeline**  
A modular Python pipeline that fetches financial and macro‑economic data from multiple public sources (Yahoo Finance, FRED, ECB, etc.) and writes normalized time‑series metrics into TimescaleDB.  The system supports both base metrics (direct API fetches) and composite metrics (Python expressions computed from other metrics). Its intended use is dashboards like Grafana, or analytics.

---

## Configuration
There are two files involve in configuration:
- [config.yaml](config.yaml) contains the non-sensitive configuration data
- [.env](.env.example) contains environment variable definitions for secrets. You can also choose to store these variables in your environment.

### Environment variables and secrets
As secrets are not to be shared, the repo only has an example .env file, which you can use as example. 

Supported entries
- `FINANCE_CONFIG`: the YAML configuration file (default config.yaml). Relative to the current directory (or absolute).
- `FRED_API_KEY`: the API key for FRED (mandatory). 
- `YAHOO_API_KEY`: the API key for Yahoo (optional).
- `TIMESCALEDB_HOST`: the TimescaleDB host e.g. `localhost`.
- `TIMESCALEDB_DB`: the database for Timescale, e.g. `finance`.
- `TIMESCALEDB_USER`: the user id
- `TIMESCALEDB_PASSWORD`: the corresponding password
- `TIMESCALEDB_SSL_MODE`: the SSL mode in PostgreSQL format. Default is `verify-full`. You can use `disable` to use plain TCP instead of TLS, or `require` to use TLS but not validate the certs. You can also use `verify-ca` to verify the CA cert but not the hostname. 
- `TIMESCALEDB_SSL_ROOT_CERT`: the location of the CA certificate to be used. If omitted, the standard CA cert storage will be used. 

Everything except the secrets (API keys, credentials) and `FINANCE_CONFIG` can also be specified in the Environment configuration section of `config.yaml`.

### Environment Configuration

This section contains settings that determine the technical setup and operation, such as like logging level, paths, and TimescaleDB settings.
Most of the timescaledb settings can also be set in .env or environment variables. If they are set in both, the yaml configuration wins.

```yaml
environment:
  logging:
    level: info
  paths:
    wal: wal.jsonl
    state: state.json
  timescaledb:
    host: localhost
    port: 5432
    ssl_mode: verify-full
    db: finance
    max_batch_size: 1000
    max_batch_age_seconds: 2.0
```
max_batch_size and max_batch_age_seconds control how often the ingested data points are persisted in the database. So in this example it is either after 1000 points were ingested, or (more than) 2 seconds passed since the last save.

### Business Configuration

This section contains the definitions of `providers` (providing the series), `assets` (series definitions) and `composites` (calculations on series), and supporting structures (`field_sets`). Composites have been disabled for the first release.

#### Providers
Three providers are currently supported: Yahoo (chart API), Fred and ECB. 
The config looks as follows:
```yaml
business:
  providers:
    yahoo:
      timeout: 10s
      sweep: 
        default: 
          window: 2h
          cadence: 30m
        1d: 
          window: 1w
          cadence: 1d
      constraints:
        history_limits:
          default: 1w
          5m: 60d
          1h: 730d
          1d: null
```
Read this as follows: for the provider Yahoo, the request timeout is 10 seconds. Fetch requests will take a sweep window of 
2 hours and will run a sweep every 30 minutes for intervals of less than a day, and a week window every day for intervals of a day or longer.
A series with an interval of less than 5 minutes has a week history limit, then for less than an hour it's 60 days, 
then for less than a day it's 730 days, and above that there is no limit.

Durations  are specified by a number and a letter, where allowed values are `m` (minutes), `h` (hours)or `d` (days) `w` (weeks) or `y` (years of 365.25 days). Internally they are translated to time deltas, so e.g. `7d` is equivalent to `1w`. 

A sweep means that already retrieved data will be retrieved again, to catch later corrections.
For ECB, the interval is 0, because ECB has a mode where you can retrieve everything that changed since a certain timestamp.
That makes the sweep unnecessary.

#### Series templates

We distinguish assets and series. Asset is a specific financial instrument, such as a share of a company, an currency exchange rate or an published interest rate.
Every asset can have one or more (usually max 2) series, a longer term one (interval 1 day or more) and a short term one with interval less than a day (intraday).

You define as them follows:

```yaml
business:
  series_templates:
    daily:
      interval: 1d
      retention: long_lived
      bootstrap_history: 10y

    intraday:
      interval: 5m
      retention: short_lived
      bootstrap_history: 30d

    candle: {}

    value: 
      series_type: value

    24x7:
      week_start: sun
      week_end: sat

    us_equities:
      timezone: America/New_York
      market_open: 09:30
      market_close: 16:00

    ecb:
      timezone: Europe/Berlin
      publication_offset: 16h
      market_open: 15:55
      market_close: 16:05
    
```

This means we define a re-usable series template named `daily` which defines an interval of a day, is long lived, and the initial fetch will be for 10 years, and another template called `intraday` with an interval of 5 minutes, short lived, and having an initial fetch of 30 days. Short-lived and long-lived determine which back-end table the series is stored into: one without retention policy or one with. 

Then we have template `candle` which only uses default values (amongst which a series_type of `candle`, which means having values [`open`, `high`, `low`, `close`, `volume`]). This can be useful to make choices explicit. Alternatively, template `value` supports only one value, which will only populate the `close` field. This is useful for instruments that don't have the full candle like the ECB USD/EUR rate, and the FRED interest rates. 

The template `24x7` defines the start of the week is Sunday and end of week is Saturday, and template `us_equities` defining a timezone, market open time and market close time (in local time). 

The `ecb` template shows the use of `publication_offset`. Normally, values are published when a series interval has completed. So e.g. the 9am interval of 5 minutes ends at 9:05 and the point is published then. For daily series, this is on the next day. However, some daily series (for example the ECB EUR/USD rates) are published at a certain time during the day (16:00 local time). That is what the publication offset specifies. If there is no publication offset, the value of the interval is taken. If there is one, it specifies the offset from midnight local time when the publication happens. It seems inconsistent to take local time, but this was done to be able to cater for daylight savings. 

You can make combined templates as well, for example 

```yaml
business:
  series_templates:
    daily_value_24x7:
      interval: 1d
      series_type: value
      week_start: sun
      week_end: sat
```

#### Assets

The asset entries specify the assets in scope along with their series.

Example:

```yaml
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
        unit: 100_troy_ounce
      series:
        intraday: [intraday, 24x7]
        daily: [daily, 24x7]
```

In this example, `gold` is the asset key, which must be unique and should not be changed after it has been ingested into the database. 
The `provider` section specifies which provider to use  and which provider code to use for fetching. The symbol here is `GOLD`. You can also omit it, and then the key (in this case `gold`) will be used instead. The tags are metadata that you can use for querying. The series section defines the series, using the series templates as defined earlier. So e.g. the `intraday` series will use the values as specified in the `intraday` and `24x7` templates. You can also make this a section with the same entries as the template instead of a reference, but for consistency and ease of usedit is recommended to use templates. 

#### Composites

_Composites have been disabled for V1. They will be re-introduced later._

Intent is to define composite data using base data or even other composites. They also have a unique user defined identifier, and always have an `expression` referring to the other identifiers. For single value series, you do not need to use the field name, for multi valued ones you do. so `fred_10y_nominal - fred_10y_breakeven` is correct assuming both identifiers exist in asset definitions. For multi-value assets, use `asset.field` as in e.g. `gold_daily.high - gold_daily.low`. Composites can also have InfluxDB `tags` and `timeseries` (daily or intraday). You can use arithmetical functions like `+`, `-`, `*`, `/`, `min`, `max`, `math.sqrt` and others. Dependencies are taken into account, and cycles will be rejected. 

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
Makefile             # testing/building/deploying the application
pyproject.toml       # project definition
pytest.ini           # pytest config
README.md            # this file
ruff.toml            # ruff (static analysis) config
```

---

## **Installation**

A makefile is provided. `make help` will provide the targets

Define `.env.prod` and `.env.acc` for production and acceptance environments. Examples are provided. Contents are simple:
```bash
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