# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/introspection.py

import inspect


def here():
    """Return the name of the current function or method."""
    return inspect.currentframe().f_back.f_code.co_name
