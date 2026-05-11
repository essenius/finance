# finance/write/controller.py

def should_write(entry, ts):
    """
    Decide whether a metric should be written to Influx.
    Returns (True/False, reason_string).
    """

    # First-time write
    if entry.get("last_value") is None:
        return True, "first-time write"

    # New timestamp → always write
    if ts != entry.get("last_timestamp"):
        return True, "new sample"

    # Same timestamp → skip
    return False, "unchanged"


def write_metric(name, value, ts, state, influx_writer):
    """
    Apply write policy and write to Influx if needed.
    Updates state when writing.
    Returns a human-readable message for logging.
    """

    entry = state.setdefault(name, {})

    ok, reason = should_write(entry, ts)
    if not ok:
        return f"{name}: {reason}"

    action = "wrote"
    try:
        influx_writer.write(name, {"value": value}, ts)
    except Exception as e:
        print(f"Influx write failed for {name}: {e}")
        action = "Influx could not write"

    entry["last_value"] = value
    entry["last_timestamp"] = ts

    return f"{name}: {action} ({value}/{ts})"
