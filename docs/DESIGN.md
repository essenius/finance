# Design Notes


## Structure

The project follows a modular architecture with distinct layers and components, organized into the following key areas:
Core Application (`src/finance/main.py`)
- Orchestrator: Coordinates data ingestion, processing, and execution. Handles fetching, state updates, and result processing (`orchestrator.py`).  
- State Management (`src/finance/state`): Manages persistent state (`state.py`) via WAL (Write-Ahead Log, `wal.py`) and backend storage.  
- Registry (`src/finance/registry`): Tracks assets, series, and metadata (`registry.py`).  
- Fetchers (`src/finance/fetch`): Retrieves data from external sources (ECB, FRED, Yahoo) via `controller.py` and provider-specific modules (`ecb.py`, `fred.py` and `yahoo.py`).  
- Timeseries Backend (`src/finance/timeseries`): Implements time-series storage and querying logic (`timescale_sql.py`, `series_backend.py`).  
- _Composites (`src/finance/composites`): Handles composite metric definitions and dependency resolution (`engine.py`). Currently disabled._
Utilities (`src/finance/common`)  
- Shared helpers for logging (`applogger.py`), time formatting (`time_utils.py`), JSON parsing (`json_utils.py`), and the canonical data model (`model.py`, `asset_metadata.py`, `candle_identity.py`, `series_calendar.py`).
Configuration (`src/finance/config`)  
- Loads and normalizes configuration from YAML files (`loader.py`).  
- Validates provider settings, retention policies, and composite definitions.
4. Tools(`tools`)
- License Management: Scripts to add license headers to files (`add_license/`).  
5. Testing (`tests`)  
- Unit test suite. Intent is to optimize defect finding capability. High coverage is a means for that, not an end.

## Design Decisions

### Date labels

Regardless of the time zone of the asset, **daily series** are stored with a date label at **midnight UTC**. This is to make it easier for downstream reporting tools to combine different series.
**Intraday series** are stored as moments (datetime) in **UTC**.

### Result handling

Operations that can fail as part of normal application flow return `Result[T]` rather than raising exceptions.

`Result[T]` is a discriminated union of `Success[T]` and `Failure`. A success contains a non-optional payload; 
a failure contains error information but no payload.

The `ok` field is a literal discriminator (`True` / `False`) so Pyright can
narrow the result type. Code that needs the payload therefore uses:

```python
if result.ok is False:
    return result

payload = result.payload
```

This syntax is intentional: it is required for Pyright's discriminated-union. Pyright will not narrow the result type 
when `result.ok` is tested using normal boolean negation (`if not result.ok`). The discriminator must be explicitly compared
with `True` or `False`.

Unexpected failures may still raise exceptions. `unwrap()` is used where failure is explicitly converted into an exception.