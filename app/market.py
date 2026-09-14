"""Data retrieval and pure, testable comparison calculations."""
from collections import namedtuple
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
    # Priced in dollars and converted on the way in; see to_twd.
    "VT": "Vanguard全世界股票",
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
    name = CATALOG.get(symbol) or (dollar_name(symbol) if currency_of(symbol) == "USD" else None)
    return f"{symbol.split('.')[0]} {name or symbol.split('.')[-1]}"


def parse_symbols(text):
    result = []
    for token in re.split(r"[,，\s]+", text.strip().upper()):
        if not token:
            continue
        if re.fullmatch(r"[A-Z]{1,5}", token):
            pass  # a US ticker, priced in dollars and converted on the way in
        elif re.fullmatch(r"\d{4,6}[A-Z]?(?:\.TW|\.TWO)?", token):
            if "." not in token:
                token = next((s for s in CATALOG if s.split('.')[0] == token), token + ".TW")
        else:
            raise ValueError(f"無效代碼：{token}。請輸入例如 2330、0050、6488.TWO 或 VT。")
        if token not in result:
            result.append(token)
    return result


# Anything without a Taiwan suffix is quoted in US dollars, and a holder in Taiwan spends
# NT$, so the two cannot sit in one portfolio untouched: VT returned 18.5% over the last
# year in dollars and 23.8% in NT$, and a blend of the first with a NT$ bond fund is a
# figure in neither currency. Conversion happens here, once, so every page inherits it.
#
# No lag. The lag belongs to a Taiwan-listed fund pricing US assets from the previous US
# close; a dollar asset's value in NT$ is its price times the rate at the same moment.
#
# Yahoo's TWD=X carries four isolated bad ticks (2011-10-25/26, 2014-12-31 and 2015-01-01,
# each dropping to about 1.8 and bouncing back). The rate has stayed between 25 and 35 for
# thirty years, so a band throws those away without touching anything real.
FX_SYMBOL = "TWD=X"
FX_FLOOR, FX_CEILING = 20.0, 40.0
TAIWAN_INDICES = {"^TWII"}


def currency_of(symbol):
    """NT$ for the Taiwan listings and the Taiwan index; US$ for everything else."""
    return "TWD" if symbol.endswith((".TW", ".TWO")) or symbol in TAIWAN_INDICES else "USD"


# Yahoo truncates shortname at this width; longname then carries the whole thing.
YAHOO_SHORTNAME_LIMIT = 31


def pick_name(quote):
    """The complete one of Yahoo's two names, preferring the shorter to read."""
    short = (quote.get("shortname") or "").strip()
    full = (quote.get("longname") or "").strip()
    if short and len(short) < YAHOO_SHORTNAME_LIMIT:
        return short
    return full or short or None


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def dollar_name(symbol):
    """Yahoo's English name for a dollar-quoted symbol, or None.

    The TWSE ISIN lists name Taiwan listings only, so this is the sole name
    source for a US ticker. A miss is cached like any other answer: label() is
    called once per pair on some tabs, and retrying there would turn a single
    Yahoo outage into a page that crawls.
    """
    try:
        quotes = yf.Search(symbol, max_results=5, news_count=0, lists_count=0,
                           recommended=0, timeout=8).quotes or []
    except Exception:
        return None
    # The search is fuzzy -- 'VO' offers VOO -- so only an exact ticker is this symbol.
    return next((pick_name(q) for q in quotes if q.get("symbol") == symbol), None)


@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
def fx_rates():
    """NT$ per US$, daily. Empty rather than raising: a page that cannot convert should
    say so through the symbol that failed, not take the whole comparison down."""
    yf.set_tz_cache_location(str(Path(tempfile.gettempdir()) / "tw-compare-yf"))
    rates = yf.Ticker(FX_SYMBOL).history(period="max", auto_adjust=False, actions=False,
                                         timeout=20)
    if rates.empty or "Close" not in rates:
        return pd.Series(dtype=float)
    close = rates["Close"].dropna()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    close = close.loc[~close.index.duplicated(keep="last")].sort_index()
    return close[(close > FX_FLOOR) & (close < FX_CEILING)]


def to_twd(history, symbol, rates=None):
    """Price a dollar-quoted history in NT$, leaving a Taiwan listing alone.

    Days the rate does not reach become NaN rather than being carried from somewhere
    plausible; the comparison already drops days a holding cannot account for, and an
    invented rate would be indistinguishable from a real one.
    """
    if currency_of(symbol) == "TWD" or history.empty:
        return history
    rates = fx_rates() if rates is None else rates
    if rates.empty:
        raise ValueError("匯率資料暫時無法取得，無法將美元計價標的換算為台幣。")
    aligned = rates.reindex(history.index.union(rates.index)).ffill().reindex(history.index)
    history = history.copy()
    for column in ("Open", "High", "Low", "Close", "Adj Close", "Dividends"):
        if column in history:
            history[column] = history[column] * aligned
    history.attrs["converted_from"] = "USD"
    return history.loc[aligned.notna()]


# Yahoo has applied some Taiwan ETF splits to only part of a series: 0050 changed units on
# 2014-01-02 and 0052 on 2025-11-17, both with an empty "Stock Splits" column. One series
# then carries two different units, and the step between them reads as a crash that never
# happened -- 0052 over the last year came out at -70.9% with a -86.6% drawdown where the
# real figures are +103.9% and -16.8%.
#
# Nothing is named here, for the reason the entry script names no modules: the symbol that
# breaks next is the one nobody remembered to list.
#
# Two signals decide, and a third only describes. A step this large is not a price move at
# all -- the daily limit is 10%, and the worst genuine day measured across 118,589 trading
# days of the catalogue is -20.0% (a 2x leveraged ETF on a -9.7% day for the index). What
# the step means is then settled by its ratio: landing on a whole number is a change of
# units, and the smallest one possible, 1:2, already moves the price 50%, so no split hides
# under the threshold. A ratio that does not land on a whole number is a stock dividend or
# something else with a story, and those are reported without being touched -- the ratio
# cannot be recovered from the series, and guessing it would erase whatever really happened.
#
# Volume is recorded but does not gate the correction. Units outstanding multiply at a
# split, and the two known cases stepped 6.4x and 12.7x against 0.54-1.33x for real falls,
# but a thinly traded fund need not show it, and requiring it is how a split gets missed.
#
# The search runs on Adj Close, which already carries the dividend adjustment. A large
# distribution moves Close by as much as a split -- 2603 fell 39.7% on 2023-06-30 -- and
# reporting those would bury the real cases in a list of ordinary ex-dividend days. The same
# day reads +10.0% once adjusted, while every genuine change of units survives adjustment
# unchanged, so the adjusted series separates the two at no cost.
SPLIT_STEP = 0.35        # the daily limit is 10%; only leveraged and foreign ETFs pass it
# The step is not the split ratio exactly: it is the ratio divided by whatever the price
# did that day, so a 1:4 on a day the fund moved 2% lands on 3.92, not 4.00. The two known
# cases moved 0.26% and 0.20% and fit inside 1%, but that was luck -- 00662 moves 1.3% on an
# ordinary day, so a 1% band would miss roughly half of its splits. Widening it alone is not
# an answer either: a stock dividend of 1.887 sits 5.7% from 2, and at 6% it would be
# "corrected" into a split it never was. So the near band decides on its own, and the wider
# one asks volume, which multiplies at a split and does not at anything else.
#
# A halt widens it further, and earns the right to. Taiwan suspends trading before a split
# and does not before a stock dividend, so halted days sitting against the step are evidence
# of the kind the ratio cannot supply. They also explain the miss: 00662 gives up four
# trading days to its 1:5 while the index it tracks keeps moving, so it resumes several
# percent away from its own reference and the step lands near 4.79 rather than 5.00. 0052
# escaped this only because its suspension fell across a weekend and cost it no session.
SPLIT_TOLERANCE = 0.01       # 0050 and 0052 land here; a whole ratio this close is decisive
SPLIT_TOLERANCE_WIDE = 0.04  # 2317's 1.887 misses 2 by 5.7%, so it stays outside
# 10% is also as far as this can go before the step starts naming the wrong ratio: a 1:5
# that drifts 11-14% lands within the band of 4 instead, and nothing in the series tells
# the two apart -- a 1:5 adrift and a 1:4 standing still leave the same step. For 00662's
# four sessions that is about 4-5 standard deviations of its index. Past 14% it falls out
# of every band and is reported instead, which is the safe way to be wrong.
SPLIT_TOLERANCE_HALT = 0.10  # only reachable with halted days against the step
SPLIT_VOLUME = 2.0           # required outside the decisive band
SPLIT_WINDOW = 20

UnitBreak = namedtuple("UnitBreak", "when divisor factor volume_step")


def unit_breaks(close, volume):
    """Days where the price steps further than a price can, in order, oldest first.

    `divisor` is what the earlier side must be divided by to join the later one, and is
    None when the step does not land on a whole ratio: those are reported, not repaired.
    A reverse split steps the other way, so a divisor below 1 multiplies the earlier side.
    """
    found = []
    for i in range(1, len(close)):
        previous, current = float(close.iloc[i - 1]), float(close.iloc[i])
        if previous <= 0 or current <= 0:
            continue
        factor = previous / current
        if 1 - SPLIT_STEP < factor < 1 / (1 - SPLIT_STEP):
            continue
        size = factor if factor > 1 else 1 / factor
        whole = round(size)
        miss = abs(size - whole) / whole if whole else 1.0
        # A halt is carried in the series as the previous close at zero volume, and a
        # split is announced with one: 00662 gives up four trading days to its 1:5. Those
        # zeros are not quiet days, they are absent ones, and a window that catches enough
        # of them would drag the median to zero and silence the corroboration.
        before = volume.iloc[max(0, i - SPLIT_WINDOW):i]
        after = volume.iloc[i:i + SPLIT_WINDOW]
        earlier, later = before[before > 0].median(), after[after > 0].median()
        step = later / earlier if earlier and earlier == earlier else None
        halted = 0
        while i - 1 - halted >= 0 and volume.iloc[i - 1 - halted] == 0:
            halted += 1
        allowed = SPLIT_TOLERANCE_WIDE if not halted else SPLIT_TOLERANCE_HALT
        near = whole >= 2 and miss <= SPLIT_TOLERANCE
        corroborated = (whole >= 2 and miss <= allowed
                        and step is not None and step >= SPLIT_VOLUME)
        divisor = (whole if factor > 1 else 1 / whole) if near or corroborated else None
        found.append(UnitBreak(close.index[i], divisor, factor, step))
    return found


def repair_units(history):
    """Put the whole series on the unit it trades in today, and record what happened.

    Rescaling the earlier side rather than the later one keeps the latest price equal to the
    real quote. Both the repairs and the steps left alone ride on the frame so the page can
    disclose either; `.attrs` survives the cache's pickling and load_frame's column select.
    """
    if "Close" not in history or "Volume" not in history:
        return history
    adjusted = "Adj Close" if "Adj Close" in history else "Close"
    found = unit_breaks(history[adjusted], history["Volume"])
    if not found:
        return history
    repaired = [b for b in found if b.divisor]
    history = history.copy()
    for unit in repaired:
        position = history.index.get_loc(unit.when)
        for column in ("Open", "High", "Low", "Close", "Adj Close"):
            if column in history:
                history.iloc[:position, history.columns.get_loc(column)] /= unit.divisor
        history.iloc[:position, history.columns.get_loc("Volume")] *= unit.divisor
    if repaired:
        history.attrs["unit_breaks"] = [(b.when, b.divisor) for b in repaired]
    unexplained = [(b.when, b.factor) for b in found if not b.divisor]
    if unexplained:
        history.attrs["unit_suspects"] = unexplained
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
    history = to_twd(repair_units(history), symbol)
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
                for kind in ("unit_breaks", "unit_suspects"):
                    if history.attrs.get(kind):
                        repaired.setdefault(kind, {})[symbol] = history.attrs[kind]
                if history.attrs.get("converted_from"):
                    repaired.setdefault("converted", {})[symbol] = history.attrs["converted_from"]
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
