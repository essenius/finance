import inspect


def here():
    """Return the name of the current function or method."""
    return inspect.currentframe().f_back.f_code.co_name
