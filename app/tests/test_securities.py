import threading
import time
from unittest.mock import patch
import pytest
import securities
from securities import (await_refresh, forget_names, load_names, parse_master,
                        snapshot_names)


@pytest.fixture(autouse=True)
def no_directory_carried_between_tests():
    forget_names()
    yield
    forget_names()


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


def test_a_name_written_as_an_entity_arrives_as_the_character():
    """The exchange escapes what HTML requires it to; a name is what it reads as."""
    html = ('<table><tr><td>0056&#12288;元大高股息&amp;收益</td><td>i</td><td>d</td>'
            '<td>上市</td><td></td><td>ESVUFR</td></tr></table>')
    assert parse_master(html, "TW") == {"0056.TW": "元大高股息&收益"}


def test_the_page_is_drawn_before_the_directory_has_been_fetched():
    """The lists take about eleven seconds. Nobody waits for them to see the page."""
    holding = threading.Event()

    def slow(suffix):
        holding.wait(10)
        return {"9999.TW": "慢慢來"}

    with patch("securities.fetch_market", side_effect=slow):
        started = time.perf_counter()
        names, failures = load_names()
        elapsed = time.perf_counter() - started
        assert elapsed < 1.0, f"load_names blocked for {elapsed:.1f}s"
        # The snapshot, in full -- not an empty dict standing in for one.
        assert names["2330.TW"] == "台積電"
        assert len(names) > 2000
        # Still running is not the same as failed, and must not be reported as one.
        assert failures == []
        holding.set()
        await_refresh()
    assert load_names()[0]["9999.TW"] == "慢慢來"


def test_a_market_that_cannot_be_reached_is_named_once_the_attempt_is_over():
    with patch("securities.fetch_market", side_effect=OSError("offline")):
        names, failures = load_names()
        assert failures == [], "nothing has failed yet on the first call"
        await_refresh()
    names, failures = load_names()
    assert names["00998A.TWO"] == "主動復華金融股息"
    assert set(failures) == {"上市", "上櫃"}


def test_one_market_failing_still_leaves_the_other_one_refreshed():
    def half(suffix):
        if suffix == "TW":
            raise OSError("offline")
        return {"6666.TWO": "只有上櫃"}

    with patch("securities.fetch_market", side_effect=half):
        load_names()
        await_refresh()
    names, failures = load_names()
    assert names["6666.TWO"] == "只有上櫃"
    assert names["2330.TW"] == "台積電", "the snapshot still covers the market that failed"
    assert failures == ["上市"]


def test_a_second_visitor_does_not_start_a_second_fetch():
    """The directory is shared by the process, not fetched once per session."""
    calls = []
    holding = threading.Event()

    def counted(suffix):
        calls.append(suffix)
        holding.wait(10)
        return {}

    with patch("securities.fetch_market", side_effect=counted):
        for _ in range(5):
            load_names()
        holding.set()
        await_refresh()
    assert sorted(calls) == ["TW", "TWO"], f"fetched more than once: {calls}"


def test_a_refresh_that_threw_says_so_instead_of_dying_in_a_log():
    """A traceback escaping the thread would leave the sidebar implying names are current."""
    with patch("securities.ThreadPoolExecutor", side_effect=RuntimeError("boom")):
        load_names()
        await_refresh()
    names, failures = load_names()
    assert set(failures) == {"上市", "上櫃"}
    assert names["2330.TW"] == "台積電", "the snapshot still carries the page"
    assert securities._refreshing is None, "the next refresh could never start"

    forget_names()
    with patch("securities.fetch_market", return_value={"1234.TW": "又試了一次"}):
        load_names()
        await_refresh()
    assert load_names()[0]["1234.TW"] == "又試了一次"


def test_a_market_that_is_down_is_retried_sooner_than_the_full_interval():
    with patch("securities.fetch_market", side_effect=OSError("offline")):
        load_names()
        await_refresh()
    assert securities.RETRY_SECONDS < securities.REFRESH_SECONDS
    # Pretend the retry window has passed; the full interval has not.
    securities._fetched_at -= securities.RETRY_SECONDS + 1
    with patch("securities.fetch_market", return_value={"5555.TW": "回來了"}):
        load_names()
        await_refresh()
    names, failures = load_names()
    assert names["5555.TW"] == "回來了"
    assert failures == []
