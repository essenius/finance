# **Finance Data Pipeline**  
A modular Python pipeline that fetches financial and macro‑economic data from multiple public sources (Yahoo Finance, FRED, ECB, etc.) and writes normalized time‑series metrics into InfluxDB.  The system supports both base metrics (direct API fetches) and composite metrics (Python expressions computed from other metrics).

The goal is a **deterministic, reliable, and extensible ingestion layer** for dashboards such as Grafana.

---

## Configuration
There are two files involve in configuration:
- [config.yaml](config.yaml) contains the non-sensitive configuration data
- [.env](.env.example) contains environment variable definitions for secrets. You can also choose to store these variables in your environment.

### Secrets
As secrets are not to be shared, the repo only has an example .env file, which you can use as example. 
Supported entries
- `FRED_API_KEY`: the API key for FRED (mandatory). 
- `YAHOO_API_KEY`: the API key for Yahoo (optional).
- `INFLUX_URL`: the base URL for InfluxDB, e.g. `https://localhost:8086`  (mandatory).
- `INFLUX_SSL_CERT`: the location of the CA certificate to be used (optional). If omitted, the standard CA cert storage will be used. This is primarily useful if the Influx server is in a local network but still using SSL
- `INFLUX_SSL_VERIFY`: the SSL verification mode. If not specified and SSL is used, True will be assumed.
    - True: standard verification
    - False: no verification (not recommended for production)
    - Legacy: verification with relaxed requirements on CA Certificates
    - Pinned: using a pinned cert (in INFLUX_SSL_CERT)

#### Influx V2
- `INFLUX_ORG`: the org to be used
- `INFLUX_WRITE_TOKEN`: the token for writing
- `INFLUX_READ_TOKEN`: the token for reading
- `INFLUX_TOKEN`: the fallback token for read or write. Only used if `INFLUX_READ_TOKEN` or `INFLUX_WRITE_TOKEN` is not specified.
It is mandatory to specify org and tokens.

#### Influx V1
- `INFLUX_DB`: the database to be used 
- `INFLUX_USER`: the user ID
- `INFLUX_PASSWORD`: the password

The existence of `INFLUX_ORG` or `INFLUX_DB` is used to determine which Influx version is used. V2 is preferred.

### Environment Configuration

This section contains settings that determine the technical setup and operation, such as like logging level, paths, influx settings and buckets

The term `bucket` maps to an InfluxDB bucket, but means more. Conceptually the system recognizes two: `daily` and `intraday`.
This was done because they have different retention policies: daily has 10y or none, and intraday usually 5 days. 
You need to define two buckets in the `buckets` subsection, and they always need two entries (one for `daily` and one for `intraday`).
They define the names of the InfluxDB buckets to be used.

If you don't consider the `url`, `org`, `db`, `ssl_cert` or `ssl_verify` locations sensitive, you can also store these in `config.yaml`, under the `influx` section.
If settings are in both locations, the one in `config.yaml` is taken.

### Business Configuration

This section contains the definitions of `providers` (providing the series), `assets` (series definitions) and `composites` (calculations on series), and supporting structures (`field_sets`)

#### Providers
Three providers are currently supported: Yahoo (chart API), Fred and ECB. 
Every provider can define a default daily and intraday history limit in `daily_history_limit` and `intraday_history_limit`. The first time an asset is fetched, it will try and fetch that limit of data. Make sure that is at most the limit that the provider allows.

#### Field sets

Daily values use the standard candle of [`open`, `high`, `low`, `close`, `volume`].
If you want to use a subset of the candle instead, you can define a new field set with e.g. only [`close`, `volume`], and the others won't be fetched for the series using that field set.

Intraday values use the field `price`.

The fields themselves cannot be changed.

#### Assets

Every asset has a unique user-defined key. It contains a `provider` (link to provider key), a `symbol` (the identifier with which the provider allows you to fetch it), `tags` (metadata stored in Influx allowing for querying), and `timeseries` (with sections `intraday` or `daily`), specifying the `interval`. That is specified by a number and a letter, where allowed values are `m` (minutes), `h` (hours)or `d` (days) `w` (weeks) or `y` (years of 365.25 days). For daily timeseries, you can define fields as a list `['close', 'volume']` or a field set reference (`candle`). If you don't specify anything, `candle` is assumed.

#### Composites

You can define composite data using base data or even other composites. They also have a unique user defined identifier, and always have an `expression` referring to the other 
identifiers. For single value series, you do not need to use the field name, for multi valued ones you do. so `fred_10y_nominal - fred_10y_breakeven` is correct assuming both
identifiers exist in asset definitions. For multi-value assets, use `asset.field` as in e.g. `gold_daily.high - gold_daily.low`. Composites can also have InfluxDB `tags` and `timeseries` (daily or intraday). You can use arithmetical functions like `+`, `-`, `*`, `/`, `min`, `max`, `math.sqrt` and others. Dependencies are taken into account, and cycles will be rejected. 


---

## Project Structure

The repository layout is as follows
```
finance/
    common/
        # shared logic
    composites/
        # dependency detection and evaluator
    config/
        # loader for config.yaml and .env, flattening structure
    fetch/
        # fetching data from the providers and transforming to standard format
    state/
        # capturing last values and timestamps per asset, caching
    timeseries/
        # reading from and writing to InfluxDB
    main_utils.py    # utilities for main
    main.py          # the main application
scripts/
    # bash scripts used by makefile
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
python -m finance.finance_data_to_influx
```

You can schedule it via cron, systemd timers, or any scheduler.

---

## **Running Tests**

The project uses **pytest**.   [Current page]
Run all tests:

```bash
pytest
```

Run a specific file:

```bash
pytest tests/test_write_influx.py
```

Ensure the package is on the Python path if needed:

```bash
PYTHONPATH=. pytest
```

---

## **Configuration**

The pipeline reads settings from:  
- `config.ini` — metric definitions, intervals, InfluxDB settings  
- `.env` — secrets and API keys  

Config is in source control, .env is not. There is .env.example that can be taken as reference. 

---

## **Contributing**

When extending the pipeline:  
- Add unit tests for new modules or behaviors  
- Keep composite expressions deterministic  
- Avoid unnecessary API calls  
- Ensure state updates follow the unified model  

  
---

## **License**

Apache License 2.0.  
See `LICENSE` for details.