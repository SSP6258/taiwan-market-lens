"""Data retrieval and pure, testable comparison calculations."""
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import json
import tempfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# Shortcuts, not a complete security master. Any Taiwan symbol can be entered.
CATALOG = {
    "00988B.TWO": "玉山嚴選非投債",
    "009828.TW": "中信台日韓PCB", "009805.TW": "台新美國電力基建",
    "00830.TW": "國泰費城半導體", "00891.TW": "中信關鍵半導體",
    "00984B.TWO": "大華優利美A債15", "0052.TW": "富邦科技",
    "009816.TW": "凱基台灣TOP50", "00685L.TW": "群益臺灣加權正2",
    "009820.TW": "元大納斯達克精選", "00635U.TW": "期元大S&P黃金",
    "8069.TWO": "元太",
    "0050.TW": "元大台灣50", "006208.TW": "富邦台50",
    "0056.TW": "元大高股息", "00878.TW": "國泰永續高股息",
    "00919.TW": "群益台灣精選高息", "00929.TW": "復華台灣科技優息",
    "00713.TW": "元大台灣高息低波", "00692.TW": "富邦公司治理",
    "00679B.TWO": "元大美債20年", "00687B.TWO": "國泰20年美債",
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科",
    "2308.TW": "台達電", "2303.TW": "聯電", "2881.TW": "富邦金",
    "2882.TW": "國泰金", "2891.TW": "中信金", "2412.TW": "中華電",
    "2603.TW": "長榮", "3008.TW": "大立光", "6488.TWO": "環球晶",
}
DEFAULT_SYMBOLS = ["0050.TW", "2330.TW", "2454.TW"]
# Optional machine-local defaults; this file is excluded from Git.
_local_defaults = Path(__file__).with_name("local_defaults.json")
if _local_defaults.exists():
    DEFAULT_SYMBOLS = json.loads(_local_defaults.read_text(encoding="utf-8"))
MAX_SYMBOLS = 12


def label(symbol):
    return f"{symbol.split('.')[0]} {CATALOG.get(symbol, symbol.split('.')[-1])}"


def parse_symbols(text):
    result = []
    for token in re.split(r"[,，\s]+", text.strip().upper()):
        if not token:
            continue
        if not re.fullmatch(r"\d{4,6}[A-Z]?(?:\.TW|\.TWO)?", token):
            raise ValueError(f"無效代碼：{token}。請輸入例如 2330、0050 或 6488.TWO。")
        if "." not in token:
            token = next((s for s in CATALOG if s.split('.')[0] == token), token + ".TW")
        if token not in result:
            result.append(token)
    return result


# Yahoo has applied some Taiwan ETF splits to only part of a series: 0050 changed units on
# 2014-01-02 and 0052 on 2025-11-17, both with an empty "Stock Splits" column. One series
# then carries two different units, and the step between them reads as a crash that never
# happened -- 0052 over the last year came out at -70.9% with a -86.6% drawdown where the
# real figures are +103.9% and -16.8%.
#
# Nothing is named here, for the reason the entry script names no modules: the symbol that
# breaks next is the one nobody remembered to list. Three signals have to agree instead, and
# across every holding in the catalogue they never overlap with a real fall -- the worst
# genuine day in the sample is -20.0% (a 2x leveraged ETF on a -9.7% day for the index) at
# 1.33x volume, against -75%/-86% at 6.4x/12.7x volume for the two splits, each landing
# within 0.3% of a whole ratio. A split Yahoo did record is already applied to Close and so
# leaves no step for this to find.
SPLIT_FALL = 0.35        # the daily limit is 10%; only leveraged and foreign ETFs pass it
SPLIT_VOLUME = 2.0       # units outstanding multiply, and the volume goes with them
SPLIT_TOLERANCE = 0.01   # the measured ratios missed 4 and 7 by 0.26% and 0.20%
SPLIT_WINDOW = 20


def unit_breaks(close, volume):
    """Days where the price switches to a smaller unit, in order, newest unit last.

    A capital reduction that returns cash also drops the price without a recorded split,
    but it does not multiply the units, so the volume test leaves it alone.
    """
    found = []
    for i in range(1, len(close)):
        previous, current = float(close.iloc[i - 1]), float(close.iloc[i])
        if previous <= 0 or current <= 0 or current / previous > 1 - SPLIT_FALL:
            continue
        ratio = previous / current
        whole = round(ratio)
        if whole < 2 or abs(ratio - whole) / whole > SPLIT_TOLERANCE:
            continue
        earlier = volume.iloc[max(0, i - SPLIT_WINDOW):i].median()
        later = volume.iloc[i:i + SPLIT_WINDOW].median()
        if not earlier or later / earlier < SPLIT_VOLUME:
            continue
        found.append((close.index[i], whole))
    return found


def repair_units(history):
    """Put the whole series on the unit it trades in today, and record what was changed.

    Rescaling the earlier side rather than the later one keeps the latest price equal to the
    real quote. The note rides on the frame so that every caller of load_symbol keeps its
    signature; `.attrs` survives both the cache's pickling and load_frame's column select.
    """
    if "Close" not in history or "Volume" not in history:
        return history
    found = unit_breaks(history["Close"], history["Volume"])
    if not found:
        return history
    history = history.copy()
    for when, whole in found:
        position = history.index.get_loc(when)
        for column in ("Open", "High", "Low", "Close", "Adj Close"):
            if column in history:
                history.iloc[:position, history.columns.get_loc(column)] /= whole
        history.iloc[:position, history.columns.get_loc("Volume")] *= whole
    history.attrs["unit_breaks"] = found
    return history


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def load_symbol(symbol: str, start: date, end: date):
    # Writable on both Windows and Community Cloud; no repository credentials.
    yf.set_tz_cache_location(str(Path(tempfile.gettempdir()) / "tw-compare-yf"))
    history = yf.Ticker(symbol).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False, actions=False, timeout=20, raise_errors=True,
    )
    if history.empty:
        raise ValueError("此區間沒有資料，請檢查市場後綴或上市日期。")
    history.index = pd.DatetimeIndex(history.index).tz_localize(None).normalize()
    history = history.loc[~history.index.duplicated(keep="last")].sort_index()
    history = repair_units(history)
    return history, datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")


def load_frame(symbols, start, end, field):
    """Fetch one price field for many symbols at once.

    Failures come back rather than raising: one delisted or mistyped symbol must not take
    the rest of the comparison with it, and the caller decides how to say so. The fourth
    value names the series whose units were repaired, so the page can disclose it.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    histories, failures, stamps, repaired = {}, {}, [], {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(load_symbol, s, start, end): s for s in symbols}
        for job in as_completed(jobs):
            symbol = jobs[job]
            try:
                history, stamp = job.result()
                if field not in history or history[field].dropna().empty:
                    raise ValueError("缺少所選價格基準資料。")
                histories[symbol] = history[field]
                stamps.append(stamp)
                if history.attrs.get("unit_breaks"):
                    repaired[symbol] = history.attrs["unit_breaks"]
            except Exception as exc:
                failures[symbol] = str(exc)
    return histories, failures, stamps, repaired


def compare_prices(prices: pd.DataFrame):
    """Use exact shared observations, never forward-fill a suspended security."""
    clean = prices.replace([np.inf, -np.inf], np.nan).where(prices > 0)
    clean = clean.sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]
    aligned = clean.dropna(how="any")
    if len(aligned) < 2 or aligned.shape[1] == 0:
        raise ValueError("共同交易日不足 2 天，請延長區間或調整標的。")
    returns = (aligned / aligned.iloc[0] - 1) * 100
    drawdown = (aligned / aligned.cummax() - 1) * 100
    days = (aligned.index[-1] - aligned.index[0]).days
    # Compute daily volatility per security, before dropping other securities' gaps.
    daily = clean.pct_change(fill_method=None).loc[aligned.index[0]:aligned.index[-1]].iloc[1:]
    stats = pd.DataFrame({
        "區間漲跌幅 (%)": returns.iloc[-1],
        "年化報酬 (%)": ((aligned.iloc[-1] / aligned.iloc[0]) ** (365.25 / days) - 1) * 100 if days >= 365 else np.nan,
        "最大回撤 (%)": drawdown.min(),
        "年化波動 (%)": daily.std(ddof=1) * np.sqrt(252) * 100,
    })
    stats.index.name = "標的"
    return aligned, returns, drawdown, stats
