from unittest.mock import patch
import pytest
from securities import parse_master, snapshot_names, load_names


def test_names_and_markets_in_official_snapshot():
    names = snapshot_names()
    assert names["00908.TW"] == "富邦入息REITs+"
    assert names["00998A.TWO"] == "主動復華金融股息"
    assert names["2330.TW"] == "台積電"
    assert len(names) > 2000


def test_master_filters_warrants_preserves_zeroes():
    html = '<table><tr><td>00908　富邦入息REITs+</td><td>ISIN</td><td>date</td><td>上市</td><td></td><td>CEOGEU</td></tr><tr><td>030001　權證</td><td>x</td><td>x</td><td>x</td><td>x</td><td>RWICPE</td></tr></table>'
    assert parse_master(html.encode("cp950"), "TW") == {"00908.TW": "富邦入息REITs+"}
    with pytest.raises(ValueError):
        parse_master('<html>service unavailable</html>', 'TW')


def test_network_failure_keeps_snapshot():
    load_names.clear()
    with patch("securities.fetch_market", side_effect=OSError("offline")):
        names, failures = load_names()
    assert names["00998A.TWO"] == "主動復華金融股息"
    assert len(failures) == 2
    load_names.clear()
