# **Finance Data Pipeline**  
A modular Python pipeline that fetches financial and macro‑economic data from multiple public sources (Yahoo Finance, FRED, ECB, U.S. Treasury, etc.) and writes normalized time‑series metrics into InfluxDB.  
The system supports both **base metrics** (direct API fetches) and **composite metrics** (Python expressions computed from other metrics).

The goal is a **deterministic, reliable, and extensible ingestion layer** for dashboards such as Grafana.

---

## **Features**
Define assets in Yaml

### **Composite Metrics With Dependency Resolution**  
Composite metrics are defined as Python expressions in config.yaml, using the asset names e.g.:  
```

assets:
  fred_10y_nominal:
    source: fred
    symbol: "DGS10"
    tags:
      symbol: 10Y_NOMINAL
      instrument: macro
      region: US
      unit: percent
      source: fred
    timeseries:
      daily:
        interval: 1d

  fred_10y_breakeven:
    source: fred
    symbol: "T10YIE"
    tags:
      symbol: 10Y_BREAKEVEN
      instrument: macro
      region: US
      unit: percent
      source: fred
    timeseries:
      daily:
        interval: 1d

composites:
  10Y_REAL:
    expression: "fred_10y_nominal - fred_10y_breakeven"
    timeseries: daily
    tags:
      symbol: 10Y_REAL
      instrument: macro
      region: US
      unit: percent
      source: composite
```

The system:  
- Parses expressions using AST  
- Extracts variable dependencies  
- Builds a dependency graph  
- Performs topological sorting  
- Evaluates composites in correct order  
- Detects and rejects cycles  


---

## **Project Structure**

The repository now follows a clean modular layout:   
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
        # capturing last values and timestamps per asset
    write/
        # writing to InfluxDB
    main.py
scripts/
    # bash scripts used by makefile
tests/
    # unit tests for finance/
tools/
    # development tools (adding license header)
config.yaml      # assets and composites, see above
.env.example     # example content for .env (secrets)
.env.acc         # environment settings for acceptance deployment
.env.prod        # environment settings for production deployment
makefile         # testing/building/deploying the application
pyproject.toml   # project definition
pytest.ini       # pytest config
ruff.toml        # ruff (static analysis) config
```

### **InfluxDB Writer (Updated)**  
The Influx writer now supports four SSL verification modes:

| Mode      | Behavior |
|-----------|----------|
| `true`    | Strict TLS, system CA store |
| `false`   | Insecure mode (`verify=False`) |
| `pinned`  | Use provided cert as trust anchor |
| `legacy`  | Custom SSLContext + adapter (OpenSSL legacy mode) |

Legacy mode uses a custom `SSLContextAdapter` and `make_legacy_ssl_context`.

---

## **Installation**

```bash
make production
cd /home/pi/prod/finance
source pyvenv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in API keys and secrets.

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