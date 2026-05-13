# **Finance Data Pipeline**  
A modular Python pipeline that fetches financial and macro‑economic data from multiple public sources (Yahoo Finance, FRED, ECB, U.S. Treasury, etc.) and writes normalized time‑series metrics into InfluxDB.  
The system supports both **base metrics** (direct API fetches) and **composite metrics** (Python expressions computed from other metrics).

The goal is a **deterministic, reliable, and extensible ingestion layer** for dashboards such as Grafana.

---

## **Features**

### **Unified State Model**  
All metrics share the same structure:  
```
state[metric] = {
    "last_value": float | None,
    "last_timestamp": int | None,
    "last_try": int | None
}
```  
This ensures consistent behavior across fetchers and composites.   [Current page](citation-section://708118277/8)

### **Freshness Based on `last_try`**  
A metric is fetched only when its freshness interval has expired:  
```
if now - last_try < interval:
    skip
```  
This applies to both base and composite metrics.   [Current page](citation-section://708118277/8)

### **Composite Metrics With Dependency Resolution**  
Composite metrics are defined as Python expressions, e.g.:  
```
SPREAD_10Y_2Y = US10Y - US2Y
```

The system:  
- Parses expressions using AST  
- Extracts variable dependencies  
- Builds a dependency graph  
- Performs topological sorting  
- Evaluates composites in correct order  
- Detects and rejects cycles  

### **Deterministic and Extensible Architecture**  
Designed to be:  
- deterministic  
- efficient  
- safe for composite‑in‑composite chains  
- easy to extend with new fetchers or metrics  


---

## **Project Structure**

The repository now follows a clean modular layout:   
```
finance/
    common/
        freshness.py
    composites/
        deps.py
        evaluator.py
    config/
        loader.py
    fetch/
        controller.py
        yahoo.py
        fred.py
        ecb.py
        treasury.py
    state/
        manager.py
    write/
        controller.py
        influx.py
        ssl_context_adapter.py
    __main__.py
    main.py
tests/
tools/
config.ini
.env.example
requirements.txt
```

### **InfluxDB Writer (Updated)**  
The Influx writer now uses a **requests.Session** with four verification modes:

| Mode      | Behavior |
|-----------|----------|
| `true`    | Strict TLS, system CA store |
| `false`   | Insecure mode (`verify=False`) |
| `pinned`  | Use provided cert as trust anchor |
| `legacy`  | Custom SSLContext + adapter (OpenSSL legacy mode) |

Legacy mode uses a custom `SSLContextAdapter` and `make_legacy_ssl_context`.

Tests mock `Session.send` to avoid real network calls and mock `make_legacy_ssl_context` inside `finance.write.influx` to avoid filesystem access.

---

## **Installation**

```bash
python -m venv .venv
source .venv/bin/activate
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