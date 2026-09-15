"""Chinese security names and Yahoo market suffixes from TWSE ISIN lists.

The lists are big -- the listed one is 8 MB of HTML -- and fetching plus parsing both of
them took about 11 seconds, which the page used to sit and wait for before it drew
anything. It does not have to: `data/securities.json` ships with the app and was measured
at 2,334 of the 2,335 names the live lists return, the odd one out being a listing from
the same week. So the snapshot answers immediately and the network copy is fetched behind
it, arriving in time for the next rerun. The page is drawn from names that are one new
listing short rather than from nothing at all.
"""
from concurrent.futures import ThreadPoolExecutor
from html import unescape
import json
from pathlib import Path
import re
import threading
import time
import requests

SNAPSHOT = Path(__file__).parent / "data/securities.json"
SOURCES = {"TW": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
           "TWO": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"}

# Read with regular expressions rather than a parser: HTMLParser visits all 8 MB a
# character at a time and spent 5.7s on the listed market where these spend 0.9s, for
# output compared byte for byte against both live lists. The page is one flat table.
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAGS = re.compile(r"<[^>]*>")
# Code and name share a cell, separated by the ideographic space the exchange writes.
_LISTING = re.compile(r"(\d{4,6}[A-Z]?)\s+(.+)")


def _text(cell):
    return _TAGS.sub("", cell).strip()


def parse_master(raw, suffix):
    text = raw.decode("cp950", errors="replace") if isinstance(raw, bytes) else raw
    result = {}
    for row in _ROW.findall(text):
        cells = _CELL.findall(row)
        # Ordinary equities and investment funds, not warrants/bonds.
        if len(cells) < 6 or not _text(cells[5]).startswith(("ES", "CE", "CI")):
            continue
        match = _LISTING.fullmatch(unescape(_text(cells[0])))
        if match and "�" not in match[2]:
            result[f"{match[1]}.{suffix}"] = match[2].strip()
    if not result:
        raise ValueError("證券名錄格式異常或沒有有效標的")
    return result


def snapshot_names():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["names"]


MARKETS = {"TW": "上市", "TWO": "上櫃"}


def fetch_market(suffix):
    response = requests.get(SOURCES[suffix], timeout=(5, 8))
    response.raise_for_status()
    return parse_master(response.content, suffix)


REFRESH_SECONDS = 21600
# A source that was down gets another chance well before the full interval; the names on
# screen are the snapshot's meanwhile, so retrying costs a reader nothing.
RETRY_SECONDS = 600

# Shared by every session in the process, so the lists are fetched once rather than once
# per visitor. `_fetched_at` is stamped by every attempt, successful or not, which is what
# keeps a market that is down from being retried on every rerun; `_refreshing` holds the
# thread doing the work so a second one is never started alongside it.
_lock = threading.Lock()
_names = None
_failed = []
_fetched_at = 0.0
_refreshing = None


def _refresh():
    global _names, _failed, _fetched_at, _refreshing
    names, failed = None, []
    try:
        fresh = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {suffix: pool.submit(fetch_market, suffix) for suffix in SOURCES}
            for suffix, job in jobs.items():
                try:
                    fresh.update(job.result())
                except Exception:
                    failed.append(MARKETS[suffix])
        names = snapshot_names()
        names.update(fresh)
    except Exception:
        # Anything else that broke belongs on the page too. Left to escape the thread, the
        # only trace of it would be a traceback in a log, while the sidebar went on
        # implying the names were current.
        failed = list(MARKETS.values())
    finally:
        with _lock:
            if names is not None:
                _names = names
            # Stamped even when nothing landed, so the next call backs off instead of
            # starting a fresh attempt on every rerun.
            _failed, _fetched_at, _refreshing = failed, time.monotonic(), None


def load_names():
    """The names to draw with, and the markets whose list could not be reached.

    Returns immediately, always: the snapshot until a refresh has landed, the refreshed
    copy afterwards. Nothing is reported as failed until a refresh has actually failed,
    so the page does not warn about a fetch that is merely still running.
    """
    global _refreshing
    starting = None
    with _lock:
        names, failed = _names, list(_failed)
        interval = RETRY_SECONDS if failed or _names is None else REFRESH_SECONDS
        due = _fetched_at == 0.0 or time.monotonic() - _fetched_at >= interval
        if due and _refreshing is None:
            starting = _refreshing = threading.Thread(target=_refresh, name="isin-refresh",
                                                      daemon=True)
    if starting is not None:
        starting.start()
    return (dict(names) if names is not None else snapshot_names()), failed


def await_refresh(timeout=30):
    """Wait for an in-flight refresh, so a test can assert on what it produced."""
    with _lock:
        thread = _refreshing
    if thread is not None:
        thread.join(timeout)


def forget_names(timeout=30):
    """Drop what has been fetched so the next call refreshes again."""
    global _names, _failed, _fetched_at
    await_refresh(timeout)
    with _lock:
        _names, _failed, _fetched_at = None, [], 0.0
