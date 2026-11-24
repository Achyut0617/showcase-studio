from showcase.pyparse import parse_python

SAMPLE = '''"""Chat server.

More detail here.
"""

def start(port=8080):
    """Start listening."""
    return port


async def ping():
    pass


class Room:
    """A chat room."""

    def join(self, user):
        pass

    async def leave(self, user):
        pass
'''


def test_symbols_and_docs():
    result = parse_python(SAMPLE)
    assert result["parse_error"] is None
    assert result["doc"] == "Chat server."
    names = [(s["name"], s["kind"]) for s in result["symbols"]]
    assert names == [
        ("start", "function"),
        ("ping", "function"),
        ("Room", "class"),
        ("Room.join", "method"),
        ("Room.leave", "method"),
    ]
    start = result["symbols"][0]
    assert start["line"] == 6 and start["doc"] == "Start listening."


def test_nested_functions_are_not_top_level_symbols():
    result = parse_python("def outer():\n    def inner():\n        pass\n")
    assert [s["name"] for s in result["symbols"]] == ["outer"]


def test_syntax_error_is_reported_not_raised():
    result = parse_python("def broken(:\n")
    assert result["symbols"] == []
    assert result["parse_error"].startswith("SyntaxError")


def test_null_bytes_are_reported_not_raised():
    assert parse_python("x = 1\x00")["parse_error"] is not None
