# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main.py

from unittest.mock import Mock

from pytest import MonkeyPatch

import finance.main as main_mod

# ----------
# test main
# ----------


def test_main_calls_run_with_correct_defaults(monkeypatch: MonkeyPatch):
    fake_run = Mock()
    monkeypatch.setattr(main_mod, "run", fake_run)

    main_mod.main([])

    assert fake_run.call_count == 1
    kwargs = fake_run.call_args.kwargs
    assert kwargs == {}
