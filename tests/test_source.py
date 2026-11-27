import pytest

from showcase.source import project_name_from_source


@pytest.mark.parametrize(
    "src,expected",
    [
        ("https://github.com/Achyut0617/NearbyConnect", "nearbyconnect"),
        ("https://github.com/Achyut0617/NearbyConnect.git", "nearbyconnect"),
        ("https://github.com/Achyut0617/NearbyConnect/", "nearbyconnect"),
        ("git@github.com:Achyut0617/StealthLedger-v1.git", "stealthledger-v1"),
        ("/home/me/My Project", "my-project"),
        ("C:\\code\\Smart_Scholar", "smart-scholar"),
        ("https://github.com/Achyut0617/NearbyConnect?tab=readme", "nearbyconnect"),
        ("https://github.com/Achyut0617/NearbyConnect#readme", "nearbyconnect"),
    ],
)
def test_project_name(src, expected):
    assert project_name_from_source(src) == expected


def test_empty_source_raises():
    with pytest.raises(ValueError):
        project_name_from_source("  ")


def test_source_with_no_usable_characters_raises():
    with pytest.raises(ValueError):
        project_name_from_source("https://github.com/!!!/")
