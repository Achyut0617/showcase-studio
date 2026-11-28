from showcase.tutorial import is_test_path, reading_order


def cm(entries, deps, hubs=()):
    mods = {}
    for a, bs in deps.items():
        mods.setdefault(a, {"depends_on": []})["depends_on"] = list(bs)
        for b in bs:
            mods.setdefault(b, {"depends_on": []})
    return {"modules": mods, "summary": {
        "entry_points": [{"path": e, "why": "x"} for e in entries],
        "hubs": [{"path": h, "used_by": 1} for h in hubs]}}


def test_is_test_path():
    assert is_test_path("src/backend/tests/test_api.py")
    assert is_test_path("web/src/App.test.tsx")
    assert is_test_path("conftest.py")
    assert not is_test_path("src/backend/routers/people.py")
    assert not is_test_path("src/latest.py")


def test_reading_order_is_breadth_first_from_entry_points_without_tests():
    m = cm(["main.py"], {"main.py": ["db.py", "routers/a.py", "tests/test_x.py"],
                         "routers/a.py": ["models/user.py", "db.py"]})
    assert reading_order(m) == ["main.py", "db.py", "routers/a.py", "models/user.py"]


def test_reading_order_falls_back_to_hubs_and_respects_limit():
    m = cm([], {"a.py": ["b.py"], "b.py": ["c.py"]}, hubs=["b.py"])
    assert reading_order(m) == ["b.py", "c.py"]
    assert reading_order(m, limit=1) == ["b.py"]
