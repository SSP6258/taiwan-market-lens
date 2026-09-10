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
    return history, datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")


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
