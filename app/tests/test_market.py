import numpy as np
import pandas as pd
import pytest
from market import compare_prices, parse_symbols


def test_common_start_and_no_filling():
    prices = pd.DataFrame({"A": [100, 110, 90, 121], "B": [np.nan, 50, np.nan, 55]}, index=pd.date_range("2024-01-01", periods=4))
    aligned, returns, drawdown, stats = compare_prices(prices)
    assert len(aligned) == 2
    assert returns.iloc[0].eq(0).all()
    assert returns.iloc[-1].tolist() == pytest.approx([10, 10])
    assert stats["年化報酬 (%)"].isna().all()


def test_drawdown_and_calendar_annualization():
    prices = pd.DataFrame({"A": [100, 120, 90, 110]}, index=pd.to_datetime(["2023-01-01", "2023-05-01", "2023-09-01", "2024-01-01"]))
    _, returns, _, stats = compare_prices(prices)
    assert stats.loc["A", "最大回撤 (%)"] == pytest.approx(-25)
    assert stats.loc["A", "年化報酬 (%)"] == pytest.approx((1.1 ** (365.25 / 365) - 1) * 100)


def test_invalid_prices_and_insufficient_overlap():
    for values in ([0, 1], [np.inf, 1], [np.nan, 1], [-1, 1]):
        with pytest.raises(ValueError):
            compare_prices(pd.DataFrame({"A": values}, index=pd.date_range("2024-01-01", periods=2)))


def test_symbol_parsing():
    assert parse_symbols("0050, 6488，00679b 0050 6510.two") == ["0050.TW", "6488.TWO", "00679B.TWO", "6510.TWO"]
    with pytest.raises(ValueError):
        parse_symbols("AAPL")
