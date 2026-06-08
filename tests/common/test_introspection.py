from finance.common.introspection import here


def test_here():
    assert here() == "test_here"
