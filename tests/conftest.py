import pytest


@pytest.fixture
def sample_source(tmp_path):
    """A tiny local project named like the real NearbyConnect, so tests stay offline."""
    root = tmp_path / "src" / "NearbyConnect"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("# NearbyConnect\n", encoding="utf-8")
    return str(root)
