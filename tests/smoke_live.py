"""Manual integration check: python -m tests.smoke_live is not required by CI."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market import load_symbol, compare_prices
import pandas as pd

symbols = ["0050.TW", "00878.TW", "2330.TW", "6488.TWO"]
def fetch(symbol):
    data, timestamp = load_symbol(symbol, date(2024, 1, 1), date(2025, 1, 1))
    assert "Adj Close" in data
    print(symbol, len(data), str(data.index.min().date()), str(data.index.max().date()))
    return data["Adj Close"]

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, symbols))
    _, returns, _, _ = compare_prices(pd.concat(dict(zip(symbols, results)), axis=1))
    assert returns.iloc[0].eq(0).all()
    assert len(returns) > 200
    print("Live data check passed:", len(returns), "shared observations")
