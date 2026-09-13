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


def test_a_real_fall_is_never_rescaled():
    """The reverse test matters more than the forward one: mistaking a fall for a split
    would erase the very drop a reader opened the page to look at. -20.0% is the worst
    genuine day measured across the catalogue, and 2603's -39.7% is a real ex-dividend."""
    for fall, ratio_note in [(0.20, "深跌，但在市場可能的範圍內"),
                             (0.397, "除息造成的真實跳動，比例非整數")]:
        index = pd.bdate_range("2024-01-01", periods=60)
        close = pd.Series([100.0] * 60, index=index)
        close.iloc[30:] = 100 * (1 - fall)
        volume = pd.Series([1000.0] * 60, index=index)
        volume.iloc[30:] = 3000.0          # a fall brings volume too; it must not decide
        frame = pd.DataFrame({"Close": close, "Adj Close": close, "Volume": volume})
        repaired = repair_units(frame)
        assert repaired["Close"].tolist() == close.tolist(), ratio_note
        assert "unit_breaks" not in repaired.attrs, ratio_note


def test_a_distribution_the_adjusted_series_absorbed_is_not_reported():
    """2603 fell 39.7% on its 2023 ex-date, as far as a split moves a price. Adjusted, the
    same day reads +10.0%. Searching the adjusted series keeps every ordinary large
    distribution out of the notice without weakening anything."""
    index = pd.bdate_range("2024-01-01", periods=60)
    close = pd.Series([100.0] * 60, index=index)
    close.iloc[30:] = 100 * (1 - 0.397)
    frame = pd.DataFrame({"Close": close, "Adj Close": pd.Series([100.0] * 60, index=index),
                          "Volume": pd.Series([1000.0] * 60, index=index)})
    repaired = repair_units(frame)
    assert "unit_breaks" not in repaired.attrs and "unit_suspects" not in repaired.attrs


def test_a_step_that_is_not_a_whole_ratio_is_reported_rather_than_guessed():
    """A stock dividend moves the price by a ratio of its own. It cannot be recovered from
    the series, so the step is named and left alone instead of being invented."""
    index = pd.bdate_range("2024-01-01", periods=60)
    close = pd.Series([100.0] * 60, index=index)
    close.iloc[30:] = 100 / 1.887                     # 2317's 2000-01-04 ratio
    frame = pd.DataFrame({"Close": close, "Adj Close": close,
                          "Volume": pd.Series([1000.0] * 60, index=index)})
    repaired = repair_units(frame)
    assert repaired["Close"].tolist() == close.tolist()
    assert "unit_breaks" not in repaired.attrs
    when, factor = repaired.attrs["unit_suspects"][0]
    assert when == index[30] and factor == pytest.approx(1.887, abs=0.01)


def test_a_split_nobody_traded_is_still_repaired():
    """Requiring a volume step is how a split gets missed: a thinly traded fund need not
    show one, and the price step alone is already beyond any real move."""
    clean, frame = split_frame(volume_step=1.0)
    repaired = repair_units(frame)
    assert repaired.attrs["unit_breaks"] == [(frame.index[30], 4)]
    assert repaired["Close"].tolist() == pytest.approx(clean.tolist())


def test_a_reverse_split_is_put_back_too():
    index = pd.bdate_range("2024-01-01", periods=60)
    clean = pd.Series([100 * 1.001 ** i for i in range(60)], index=index)
    raw = clean.copy()
    raw.iloc[:30] /= 3                                 # 3 old units became 1 new one
    frame = pd.DataFrame({"Close": raw, "Adj Close": raw,
                          "Volume": pd.Series([1000.0] * 60, index=index)})
    repaired = repair_units(frame)
    when, divisor = repaired.attrs["unit_breaks"][0]
    assert when == index[30] and divisor == pytest.approx(1 / 3)
    assert repaired["Close"].tolist() == pytest.approx(clean.tolist())


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


def test_a_split_on_a_day_the_fund_moved_is_still_recognised():
    """The step is the ratio divided by that day's own move, so a 1:4 on a 2% day lands on
    3.92 rather than 4.00. Measured against 00662, a 1% band alone catches two thirds of
    split dates; with the volume step to corroborate the wider band it catches all of them."""
    index = pd.bdate_range("2024-01-01", periods=60)
    clean = pd.Series([100 * 1.001 ** i for i in range(60)], index=index)
    raw = clean.copy()
    raw.iloc[30] *= 1.025                      # the fund rose 2.5% on the day it split
    raw.iloc[:30] *= 4
    volume = pd.Series([1000.0] * 60, index=index)
    volume.iloc[:30] = 250.0
    frame = pd.DataFrame({"Close": raw, "Adj Close": raw, "Volume": volume})
    repaired = repair_units(frame)
    assert repaired.attrs["unit_breaks"] == [(index[30], 4)]
    # Without the volume step the ratio alone is too far out, and it is reported instead.
    flat = pd.DataFrame({"Close": raw, "Adj Close": raw,
                         "Volume": pd.Series([1000.0] * 60, index=index)})
    quiet = repair_units(flat)
    assert "unit_breaks" not in quiet.attrs
    assert quiet.attrs["unit_suspects"][0][0] == index[30]


def halted_split(drift, halted_days, ratio=5):
    """Taiwan suspends trading before a split, and the index it tracks keeps moving, so the
    fund resumes away from its own reference price and the step misses the whole ratio."""
    index = pd.bdate_range("2026-08-03", "2026-12-31")
    close = pd.Series([100 * 1.0005 ** i for i in range(len(index))], index=index)
    volume = pd.Series([1000.0] * len(index), index=index)
    resume = index.get_loc(pd.Timestamp("2026-11-17"))
    for day in range(resume - halted_days, resume):
        close.iloc[day] = close.iloc[resume - halted_days - 1]
        volume.iloc[day] = 0.0                      # a halt is carried at zero volume
    close.iloc[resume:] *= 1 + drift
    close.iloc[resume:] /= ratio
    volume.iloc[resume:] *= ratio
    return index[resume], pd.DataFrame({"Close": close, "Adj Close": close, "Volume": volume})


def test_a_split_behind_a_halt_is_recognised_despite_the_drift():
    """00662's announced 1:5 gives up four sessions, and 4.8% of index drift across them
    puts the step on 4.77 rather than 5.00 -- outside the band a split without a halt gets.
    The halted days are the evidence: a stock dividend never has any."""
    when, frame = halted_split(drift=0.048, halted_days=4)
    assert repair_units(frame).attrs["unit_breaks"] == [(when, 5)]
    # The same drift with no halt behind it stays a report, not a repair.
    _, unhalted = halted_split(drift=0.048, halted_days=0)
    repaired = repair_units(unhalted)
    assert "unit_breaks" not in repaired.attrs
    assert repaired.attrs["unit_suspects"]


def test_a_halt_does_not_licence_any_ratio():
    """The widened band is still a band. Drift far enough and the step falls between whole
    ratios, and a step that names nothing is reported rather than rounded to a guess.

    Drift further still and it reaches the next whole ratio down and is named wrongly -- a
    1:5 adrift and a 1:4 standing still leave the same step, and no part of the series tells
    them apart. For 00662 that takes 11-14% across four sessions, four to five standard
    deviations of the index it tracks; the band stops just short of it deliberately."""
    when, frame = halted_split(drift=0.124, halted_days=4)
    repaired = repair_units(frame)
    assert "unit_breaks" not in repaired.attrs
    assert repaired.attrs["unit_suspects"][0][0] == when
