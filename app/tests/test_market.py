import numpy as np
import pandas as pd
import pytest
from market import compare_prices, parse_symbols, repair_units, unit_breaks


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


def split_frame(break_at=30, ratio=4, volume_step=4.5, periods=60):
    """A clean series that Yahoo would hand back with two different units in it:
    everything before the split is still quoted in the pre-split unit."""
    index = pd.bdate_range("2024-01-01", periods=periods)
    close = pd.Series([100 * 1.001 ** i for i in range(periods)], index=index)
    raw = close.copy()
    raw.iloc[:break_at] *= ratio
    volume = pd.Series([1000.0] * periods, index=index)
    volume.iloc[:break_at] = 1000.0 / volume_step
    return close, pd.DataFrame({"Close": raw, "Adj Close": raw * 0.9, "Volume": volume})


def test_an_unrecorded_split_is_put_back_on_one_unit():
    clean, frame = split_frame()
    repaired = repair_units(frame)
    assert repaired.attrs["unit_breaks"] == [(frame.index[30], 4)]
    assert repaired["Close"].tolist() == pytest.approx(clean.tolist())
    # The junction must stop reading as a crash.
    assert repaired["Close"].pct_change().min() > -0.01
    # Today's quote is the real one; it is the history that moves onto its unit.
    assert repaired["Close"].iloc[-1] == pytest.approx(frame["Close"].iloc[-1])


def test_a_real_crash_is_never_rescaled():
    """The reverse test matters more than the forward one: mistaking a crash for a split
    would erase the very fall a reader opened the page to look at."""
    for fall, volume_ratio, note in [(0.20, 1.3, "深跌但未達門檻"),
                                     (0.75, 1.0, "跌幅與比例都像分割，但股數沒有變"),
                                     (0.60, 3.0, "量能跳升，但比例不是整數")]:
        index = pd.bdate_range("2024-01-01", periods=60)
        close = pd.Series([100.0] * 60, index=index)
        close.iloc[30:] = 100 * (1 - fall)
        volume = pd.Series([1000.0] * 60, index=index)
        volume.iloc[30:] = 1000.0 * volume_ratio
        frame = pd.DataFrame({"Close": close, "Adj Close": close, "Volume": volume})
        repaired = repair_units(frame)
        assert repaired["Close"].tolist() == close.tolist(), note
        assert "unit_breaks" not in repaired.attrs, note


def test_every_break_in_one_series_is_repaired():
    index = pd.bdate_range("2024-01-01", periods=90)
    close = pd.Series([100 * 1.001 ** i for i in range(90)], index=index)
    raw, volume = close.copy(), pd.Series([1000.0] * 90, index=index)
    raw.iloc[:60] *= 2           # the later split
    raw.iloc[:30] *= 4           # and an earlier one, compounding
    volume.iloc[:60] /= 2
    volume.iloc[:30] /= 4
    repaired = repair_units(pd.DataFrame({"Close": raw, "Volume": volume}))
    assert [whole for _, whole in repaired.attrs["unit_breaks"]] == [4, 2]
    assert repaired["Close"].tolist() == pytest.approx(close.tolist())


def test_a_series_nobody_split_is_left_exactly_alone():
    index = pd.bdate_range("2024-01-01", periods=40)
    close = pd.Series([100 * 1.002 ** i for i in range(40)], index=index)
    frame = pd.DataFrame({"Close": close, "Volume": pd.Series([1000.0] * 40, index=index)})
    repaired = repair_units(frame)
    assert repaired is frame
    assert unit_breaks(frame["Close"], frame["Volume"]) == []
