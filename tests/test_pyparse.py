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


def test_imports_collected_including_lazy_ones():
    text = (
        "import os, json as j\n"
        "from .models import User, Room\n"
        "from .. import config\n"
        "def f():\n"
        "    import requests\n"
    )
    imps = parse_python(text)["imports"]
    assert [(i["module"], i["names"], i["level"]) for i in imps] == [
        ("os", [], 0),
        ("json", [], 0),
        ("models", ["User", "Room"], 1),
        ("", ["config"], 2),
        ("requests", [], 0),
    ]


def test_main_guard_detected():
    assert parse_python('if __name__ == "__main__":\n    main()\n')["main_guard"] is True
    assert parse_python("x = 1\n")["main_guard"] is False


def test_resolve_absolute_import():
    from showcase.pyparse import resolve_import

    imp = {"module": "app.db", "names": ["connect"], "level": 0}
    assert resolve_import(imp, "app.main", False) == ["app.db.connect", "app.db"]


def test_resolve_relative_imports():
    from showcase.pyparse import resolve_import

    sib = {"module": "models", "names": ["User"], "level": 1}
    assert resolve_import(sib, "app.api.views", False) == ["app.api.models.User", "app.api.models"]
    assert resolve_import(sib, "app.api", True) == ["app.api.models.User", "app.api.models"]
    up = {"module": "", "names": ["config"], "level": 2}
    assert resolve_import(up, "app.api.views", False) == ["app.config", "app"]


def test_relative_import_beyond_top_resolves_to_nothing():
    from showcase.pyparse import resolve_import

    assert resolve_import({"module": "x", "names": [], "level": 5}, "a.b", False) == []


def test_calls_recorded_per_function():
    text = (
        "def save(x):\n"
        "    db.session.add(x)\n"
        "    validate(x)\n"
        "    validate(x)\n"
        "    handlers[0](x)\n"
        "class Room:\n"
        "    def join(self, u):\n"
        "        self.notify(u)\n"
        "        log(u)\n"
    )
    syms = {s["name"]: s for s in parse_python(text)["symbols"]}
    assert syms["save"]["calls"] == ["db.session.add", "validate"]
    assert syms["Room.join"]["calls"] == ["log", "self.notify"]
    assert syms["Room"]["calls"] == []
