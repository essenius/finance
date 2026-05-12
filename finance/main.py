#!/usr/bin/env python3
# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/main.py

from .composites.evaluator import evaluate_composites
from .config.loader import load_config
from .fetch.controller import FetchController
from .state.manager import load_state, save_state
from .write.controller import write_metric
from .write.influx import InfluxWriter


def main():

    config = load_config()

    symbols = config["symbols"]
    composites = config["composites"]
    secrets = config["secrets"]

    print(f"Config loaded. Symbols: {list(symbols.keys())}, Composites: {list(composites.keys())}, Secrets: {secrets}")

    state = load_state()
    influx_writer = InfluxWriter(secrets["influx"])

    fetch_controller = FetchController(symbols, secrets["api_keys"])
    fetched = fetch_controller.fetch_all(state)

    # Write fetched data to Influx and update state
    for name, (value, ts) in fetched.items():
        msg = write_metric(name=name, value=value, ts=ts, state=state, influx_writer=influx_writer)
        print(msg)

    computed = evaluate_composites(composites, state)

    # Write composites
    for name, (value, ts) in computed.items():
        msg = write_metric(name=name, value=value, ts=ts, state=state, influx_writer=influx_writer)
        print(msg)

    save_state(state)
    print("Done.")

if __name__ == "__main__":
    main()
