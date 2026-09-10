"""Chinese security names and Yahoo market suffixes from TWSE ISIN lists."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import requests
import streamlit as st

SNAPSHOT = Path(__file__).parent / "data/securities.json"
SOURCES = {"TW": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
           "TWO": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"}


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.parts = [], [], []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th"):
            self.in_cell, self.parts = True, []

    def handle_data(self, data):
        if self.in_cell:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.row.append("".join(self.parts).strip())
            self.in_cell = False
        if tag == "tr" and self.row:
            self.rows.append(self.row)


def parse_master(raw, suffix):
    parser = TableRows()
    parser.feed(raw.decode("cp950", errors="replace") if isinstance(raw, bytes) else raw)
    result = {}
    for row in parser.rows:
        if len(row) < 6 or not row[5].startswith(("ES", "CE", "CI")):
            continue  # Ordinary equities and investment funds, not warrants/bonds.
        match = re.fullmatch(r"(\d{4,6}[A-Z]?)\s+(.+)", row[0])
        if match and "�" not in match[2]:
            result[f"{match[1]}.{suffix}"] = match[2].strip()
    if not result:
        raise ValueError("證券名錄格式異常或沒有有效標的")
    return result


def snapshot_names():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["names"]


def fetch_market(suffix):
    response = requests.get(SOURCES[suffix], timeout=(5, 8))
    response.raise_for_status()
    return parse_master(response.content, suffix)


@st.cache_data(ttl=21600, max_entries=1, show_spinner=False)
def load_names():
    names = snapshot_names()
    failed = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {suffix: pool.submit(fetch_market, suffix) for suffix in SOURCES}
        for suffix, job in jobs.items():
            try:
                names.update(job.result())
            except Exception:
                failed.append("上市" if suffix == "TW" else "上櫃")
    return names, failed
