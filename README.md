# Finance Data Pipeline

A modular Python pipeline that fetches financial and macro‑economic data from multiple public sources (Yahoo Finance, FRED, ECB, U.S. Treasury, etc.) and writes the results to InfluxDB. The system supports both **base metrics** (fetched directly from APIs) and **composite metrics** (computed from other metrics using Python expressions).

The goal is to provide a reliable, deterministic, and extensible ingestion layer for time‑series dashboards such as Grafana.

---

## Features

### Unified state model

All metrics share the same state structure:

```python
state[metric] = {
    "last_value": float | None,
    "last_timestamp": int | None,
    "last_try": int | None
}
```

This ensures consistent behavior across base and composite metrics.

### Freshness based on `last_try`

To avoid unnecessary API calls, each metric is fetched only when its freshness interval has expired:

```text
if now - last_try < interval:
    skip
```

This applies to both base metrics and composites.

### Composite metrics with dependency resolution

Composite metrics are defined as Python expressions, for example:

```text
SPREAD_10Y_2Y = US10Y - US2Y
```

The system:

- **Parses expressions with AST** to extract variable dependencies.
- **Builds a dependency graph** of composite metrics.
- **Topologically sorts** the graph to determine evaluation order.
- **Evaluates composites** in dependency order.
- **Detects and rejects cycles** in composite definitions.

### Deterministic and extensible

The architecture is designed to be:

- deterministic  
- efficient  
- safe for composite‑in‑composite chains  
- easy to extend with new fetchers or metrics  

---

## Project structure

A suggested structure for the repository:

```text
finance/                     # repo root
    finance/                 # Python package
        __init__.py
        finance_data_to_influx.py     # main pipeline script

        composites/
            __init__.py
            topo.py                   # topo_sort + cycle detection
            parser.py                 # AST dependency extraction
            evaluator.py              # composite evaluation

        state/
            __init__.py
            model.py                  # state structure
            process.py                # process_metric()

        fetchers/
            __init__.py
            yahoo.py
            fred.py
            ecb.py
            treasury.py

        writers/
            __init__.py
            influx.py                 # InfluxDB writer

    config.ini
    .env

    tests/
        __init__.py
        test_topo_sort.py
```

This layout keeps the pipeline modular and testable while remaining small and understandable.

---

## Installation

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` (if present) and fill in any required API keys or secrets.

---

## Running the pipeline

From the project root:

```bash
python -m finance.finance_data_to_influx
```

You can schedule this via cron, systemd timers, or any other scheduler.

---

## Running tests

The project uses `pytest`.

Run all tests:

```bash
pytest
```

Run a specific test file:

```bash
pytest tests/test_topo_sort.py
```

If needed, you can ensure the package is on the Python path:

```bash
PYTHONPATH=. pytest
```

---

## Configuration

The pipeline reads settings from:

- `config.ini` — metric definitions, intervals, InfluxDB settings  
- `.env` — secrets and API keys  

Both files are intentionally excluded from version control.

---

## Contributing

When extending the pipeline:

- Add unit tests for new modules or behaviors.
- Keep composite expressions deterministic and side‑effect free.
- Avoid unnecessary API calls; respect freshness intervals.
- Ensure state updates follow the unified state model.

---

## License

This project is licensed under the Apache License 2.0.
See the LICENSE file for details.
