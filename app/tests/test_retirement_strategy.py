import pandas as pd
import pytest
from allocation import PRESETS
from retirement_strategy import (BACKTEST_DEFAULT, BACKTEST_NOTES, BACKTEST_PRESETS,
                                 BUFFER_YIELD, HELD_FRACTION, ORIGINAL,
                                 POSTER, PRESET, WITHDRAW_RATE, backtest,
                                 backtest_holdings, growth_share, income_chart,
                                 month_ends, monthly_execution_gain, pool_plan,
                                 yearly_income, EPISODE_NAMES, drawdown_episodes,
                                 worst_fall_without_the_currency, INCOME_COLOUR,
                                 TRANSFER_COLOUR, ORDINARY_MONTH, TRANSFER_MONTH,
                                 compare_presets, shared_window)


def test_the_original_ratio_pays_out_exactly_what_it_moved_in():
    """100:12 is not an arbitrary split: the buffer holds three years of spending, so the
    year's transfer and the year's withdrawal are the same number and the buffer holds."""
    plan = pool_plan(3000 * 10000, growth_share(ORIGINAL))
    assert plan["spend"] == pytest.approx(plan["transfer"])
    assert plan["buffer_years"] == pytest.approx(3.0)
    assert plan["buffer_left"] == pytest.approx(plan["buffer"])
    assert plan["spend"] / 10000 == pytest.approx(107.14, abs=0.01)   # the figure on the poster
    assert plan["monthly"] / 10000 == pytest.approx(8.93, abs=0.01)


def test_the_preset_ratio_is_read_off_the_preset_not_restated():
    """The page must follow 退休5 if its weights are ever edited, rather than drift from it."""
    assert growth_share(PRESET) == pytest.approx(PRESETS["退休5"]["weights"]["009826.TW"] / 100)
    plan = pool_plan(3000 * 10000, growth_share(PRESET))
    assert plan["growth"] / 10000 == pytest.approx(2700)
    assert plan["buffer"] / 10000 == pytest.approx(300)
    assert plan["spend"] / 10000 == pytest.approx(102)


def test_the_rounder_ratio_leaves_the_buffer_a_little_short_of_three_years():
    """90:10 spends slightly less than it moves in, so the buffer creeps up rather than down.
    Worth pinning: it is the difference between the poster and what the app actually presets."""
    plan = pool_plan(3000 * 10000, growth_share(PRESET))
    assert plan["spend"] < plan["transfer"]
    assert plan["buffer_left"] > plan["buffer"]
    assert plan["buffer_years"] == pytest.approx(2.94, abs=0.01)


def test_nothing_is_created_or_lost_in_a_year():
    plan = pool_plan(3000 * 10000, growth_share(ORIGINAL))
    assert plan["growth_left"] + plan["buffer_left"] + plan["spend"] == pytest.approx(3000 * 10000)


def test_the_spending_rate_scales_with_the_principal_but_the_share_does_not():
    small, large = pool_plan(1000 * 10000, 0.9), pool_plan(9000 * 10000, 0.9)
    assert large["spend"] == pytest.approx(small["spend"] * 9)
    assert large["spend_rate"] == pytest.approx(small["spend_rate"])


def test_an_empty_principal_does_not_divide_by_zero():
    plan = pool_plan(0, growth_share(ORIGINAL))
    assert plan["spend"] == 0
    assert plan["buffer_years"] != plan["buffer_years"]   # NaN, not a crash


def test_the_poster_the_page_shows_is_still_where_the_page_looks():
    """The page degrades to a notice if it is gone, which is easy not to notice. It lives in
    analysis/ with the study that produced it, so it is a runtime asset of the app as well."""
    assert POSTER.exists(), POSTER
    assert POSTER.stat().st_size > 100_000


def test_spreading_the_withdrawal_is_worth_the_months_it_stays_invested():
    """Derive the 11/24 rather than take it on trust. A lump sum at the start of the year is
    out of the pool for the whole year; a twelfth drawn each month leaves the rest earning."""
    lump = 1.0
    monthly = sum((1 - month / 12) / 12 for month in range(12))
    assert lump - monthly == pytest.approx(HELD_FRACTION)

    spend = pool_plan(3000 * 10000, growth_share(PRESET))["spend"]
    gain = monthly_execution_gain(spend)
    assert gain == pytest.approx(spend * BUFFER_YIELD * HELD_FRACTION)
    assert gain / 10000 == pytest.approx(1.35, abs=0.01)
    assert gain < spend * BUFFER_YIELD   # never more than a full year of the buffer's return


def test_taking_a_quarter_every_month_would_be_a_different_rule_not_a_schedule():
    """The page warns about this because it is the easy mistake to make: 25% is an annual
    rate. Applied monthly it takes almost the entire buffer inside one year."""
    assert 1 - (1 - WITHDRAW_RATE) ** 12 == pytest.approx(0.968, abs=0.001)


def _flat(months=40, growth_step=0.0, buffer_step=0.0, start='2020-01-01'):
    """Daily series whose month-on-month move is exactly the step asked for."""
    index = pd.date_range(start, periods=months, freq='ME')
    growth = pd.Series([100 * (1 + growth_step) ** i for i in range(months)], index=index)
    buffer = pd.Series([50 * (1 + buffer_step) ** i for i in range(months)], index=index)
    return growth, buffer


def test_the_first_year_of_the_backtest_is_the_arithmetic_on_the_page():
    """The chart and the table above it have to be the same rule, or one of them is lying."""
    growth, buffer = _flat()
    run = backtest(growth, buffer, 3000 * 10000, growth_share(PRESET))
    plan = pool_plan(3000 * 10000, growth_share(PRESET))
    assert run['年生活費'].iloc[0] == pytest.approx(plan['spend'])
    assert run['當月生活費'].iloc[0] == pytest.approx(plan['monthly'])


def test_the_year_s_amount_does_not_move_when_the_market_does():
    """Fixed on the anniversary and then left alone -- that is the whole point of the buffer.
    A crash inside the year must not change the twelve payments already decided."""
    index = pd.date_range('2020-01-01', periods=30, freq='ME')
    prices = [100.0] * 30
    for i in range(4, 30):
        prices[i] = 55.0          # a 45% fall in month 4, held
    growth = pd.Series(prices, index=index)
    buffer = pd.Series([50.0] * 30, index=index)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    first_year = run['當月生活費'].iloc[:12]
    assert first_year.nunique() == 1, '年度金額在年中被市場改掉了'
    # The next anniversary is where it is allowed to notice, and it must.
    assert run['當月生活費'].iloc[12] < first_year.iloc[0]


def test_nothing_is_created_or_lost_over_the_whole_run():
    growth, buffer = _flat(months=37)
    principal = 3000 * 10000
    run = backtest(growth, buffer, principal, 0.9)
    assert run['總資產'].iloc[-1] + run['當月生活費'].sum() == pytest.approx(principal)


def test_the_buffer_is_never_overdrawn():
    """At a low transfer rate the buffer thins; paying out of an empty one would be a loan."""
    growth, buffer = _flat(months=120)
    run = backtest(growth, buffer, 3000 * 10000, 0.9, transfer_rate=0.01)
    assert (run['緩衝池'] >= -1e-6).all()
    assert (run['當月生活費'] >= 0).all()


def test_a_larger_transfer_rate_buys_income_with_the_principal():
    growth, buffer = _flat(months=85, growth_step=0.004)
    lean = backtest(growth, buffer, 3000 * 10000, 0.9, transfer_rate=0.02)
    rich = backtest(growth, buffer, 3000 * 10000, 0.9, transfer_rate=0.07)
    assert rich['當月生活費'].sum() > lean['當月生活費'].sum()
    assert rich['總資產'].iloc[-1] < lean['總資產'].iloc[-1]


def test_a_history_too_short_to_hold_a_year_is_refused():
    growth, buffer = _flat(months=12)
    with pytest.raises(ValueError):
        backtest(growth, buffer, 3000 * 10000, 0.9)


def test_the_part_year_at_the_end_is_not_counted_as_a_year_of_income():
    """83 months is six whole years and eleven months; the tail would read as a collapse."""
    growth, buffer = _flat(months=83)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    paid = yearly_income(run)
    assert len(paid) == 6
    assert paid.iloc[-1] == pytest.approx(run['當月生活費'].iloc[60:72].sum())


def test_one_row_per_month_and_no_month_invented():
    """A month the market never traded must not appear as a month the pools were worth zero."""
    index = pd.DatetimeIndex(['2020-01-06', '2020-01-31', '2020-02-28', '2020-05-29'])
    growth = pd.Series([10.0, 11.0, 12.0, 13.0], index=index)
    buffer = pd.Series([5.0, 5.1, 5.2, 5.3], index=index)
    monthly = month_ends(growth, buffer)
    assert len(monthly) == 3
    assert monthly['growth'].tolist() == [11.0, 12.0, 13.0]


def test_the_backtest_holdings_are_read_off_the_preset():
    for preset in BACKTEST_PRESETS:
        growth, buffer = backtest_holdings(preset)
        weights = PRESETS[preset]['weights']
        assert weights[growth] > weights[buffer], preset
        assert set([growth, buffer]) == set(weights), preset
    assert backtest_holdings() == backtest_holdings(BACKTEST_DEFAULT)


def test_the_two_readings_keep_their_own_scales():
    """One scale would flatten a month's living costs against the principal behind it."""
    growth, buffer = _flat(months=40)
    chart = income_chart(backtest(growth, buffer, 3000 * 10000, 0.9))
    assert len(chart.layer) == 2
    assert chart.resolve.scale.y == 'independent'


def _fall(shape, start='2020-01-01'):
    index = pd.bdate_range(start, periods=len(shape))
    return pd.Series([float(v) for v in shape], index=index)


def test_a_fall_is_measured_from_the_high_it_fell_from_to_the_day_it_got_back():
    prices = _fall([100, 100, 80, 70, 75, 90, 100, 101])
    found = drawdown_episodes(prices, threshold=0.08)
    assert len(found) == 1
    episode = found[0]
    assert episode['跌幅'] == pytest.approx(-0.30)
    assert episode['高點'] == prices.index[1]
    assert episode['谷底'] == prices.index[3]
    assert episode['收復'] == prices.index[6]


def test_a_wobble_shallower_than_the_threshold_is_not_an_episode():
    assert drawdown_episodes(_fall([100, 96, 98, 100, 101]), threshold=0.08) == []
    assert len(drawdown_episodes(_fall([100, 90, 95, 100, 101]), threshold=0.08)) == 1


def test_a_fall_still_running_at_the_end_says_it_has_not_recovered():
    """Taking the last row as the recovery would turn an open drawdown into a closed one."""
    found = drawdown_episodes(_fall([100, 100, 70, 75, 80]), threshold=0.08)
    assert len(found) == 1
    assert found[0]['收復'] is None
    assert found[0]['跌幅'] == pytest.approx(-0.30)


def test_a_trough_inside_a_month_survives_daily_sampling():
    """Month ends called COVID a 22.3% fall where it was 33.6%; the page shades the real one."""
    daily = _fall([100] * 5 + [66] + [95] * 5 + [101])
    monthly = daily.groupby(daily.index.to_period('M')).last()
    assert drawdown_episodes(daily, threshold=0.08)[0]['跌幅'] == pytest.approx(-0.34)
    assert not drawdown_episodes(monthly, threshold=0.30)


def test_an_episode_is_only_named_when_its_trough_is_one_we_know():
    known = next(iter(EPISODE_NAMES))
    index = pd.bdate_range(f'{known[0]}-{known[1]:02d}-01', periods=6)
    named = drawdown_episodes(pd.Series([100.0, 100.0, 70.0, 80.0, 95.0, 101.0], index=index))
    assert named[0]['名稱'] == EPISODE_NAMES[known]
    plain = drawdown_episodes(_fall([100, 100, 70, 80, 95, 101], start='2017-03-01'))
    assert plain[0]['名稱'] is None, '認不出來的就該留白，不是編一個'


def test_only_the_deep_episodes_get_shaded():
    growth, buffer = _flat(months=40)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    shallow = [{'高點': run.index[2], '谷底': run.index[4], '收復': run.index[8],
                '跌幅': -0.09, '名稱': None}]
    deep = [dict(shallow[0], 跌幅=-0.30, 名稱='測試事件')]
    assert len(income_chart(run, shallow).layer) == len(income_chart(run).layer)
    assert len(income_chart(run, deep).layer) > len(income_chart(run).layer)


def test_a_rate_move_is_not_the_bond_falling():
    """00865B lost 12.1% in NT$ over 2025 while gaining 0.8% in dollars. The buffer is the
    part meant to hold still, so which of the two it was has to be said out loud."""
    index = pd.bdate_range('2025-01-01', periods=6)
    rates = pd.Series([33.0, 33.0, 31.0, 29.0, 29.0, 29.0], index=index)
    steady_in_dollars = pd.Series([100.0, 100.0, 94.0, 88.0, 88.0, 88.0], index=index)
    told = worst_fall_without_the_currency(steady_in_dollars, rates)
    assert told['跌幅'] == pytest.approx(-0.12, abs=0.005)
    assert told['美元計價'] == pytest.approx(0.0, abs=0.005)


def test_without_a_rate_series_it_declines_to_guess():
    prices = _fall([100, 90, 80, 85])
    assert worst_fall_without_the_currency(prices, pd.Series(dtype=float)) is None
    assert worst_fall_without_the_currency(prices, None) is None


def test_the_transfer_happens_once_a_year_and_only_then():
    growth, buffer = _flat(months=37, growth_step=0.003)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    marked = [i for i, flag in enumerate(run['撥款月']) if flag]
    assert marked == [0, 12, 24, 36]
    assert (run.loc[run['撥款月'], '當月撥款'] > 0).all()
    assert (run.loc[~run['撥款月'], '當月撥款'] == 0).all()


def test_the_first_transfer_is_the_one_the_table_above_the_chart_shows():
    growth, buffer = _flat(months=20)
    run = backtest(growth, buffer, 3000 * 10000, growth_share(PRESET))
    plan = pool_plan(3000 * 10000, growth_share(PRESET))
    assert run['當月撥款'].iloc[0] == pytest.approx(plan['transfer'])


def test_the_marked_month_pays_the_same_as_the_eleven_after_it():
    """The colour says a decision was made that month, not that more money came out. A bar
    that was actually taller would be telling the reader something that is not true."""
    growth, buffer = _flat(months=26, growth_step=0.004)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    first_year = run['當月生活費'].iloc[:12]
    assert first_year.nunique() == 1
    assert run['撥款月'].iloc[0] and not run['撥款月'].iloc[1:12].any()


def test_the_chart_colours_the_transfer_month_apart_from_the_rest():
    """Asserted on the compiled spec rather than the builder: the spec is what gets drawn."""
    growth, buffer = _flat(months=26)
    spec = income_chart(backtest(growth, buffer, 3000 * 10000, 0.9)).to_dict()
    bars = next(layer for layer in spec['layer']
                if (layer['mark']['type'] if isinstance(layer['mark'], dict)
                    else layer['mark']) == 'bar')
    colour = bars['encoding']['color']
    assert colour['field'] == '月份類型'
    assert colour['scale']['domain'] == [ORDINARY_MONTH, TRANSFER_MONTH]
    assert colour['scale']['range'] == [INCOME_COLOUR, TRANSFER_COLOUR]
    # Two colours with nothing saying which is which are decoration, not information.
    assert colour.get('legend') is not None


def test_the_transfer_is_january_whatever_month_the_data_opens_in():
    """The real history opens in November. Counting twelve from there would put the transfer
    in November forever -- a date that means nothing to anyone holding this."""
    index = pd.date_range('2019-11-01', periods=40, freq='ME')
    growth = pd.Series([100 * 1.004 ** i for i in range(40)], index=index)
    buffer = pd.Series([50.0] * 40, index=index)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    assert run.index[0].month == 1 and run.index[0].year == 2020, run.index[0]
    assert all(when.month == 1 for when in run.index[run['撥款月']])
    assert run['撥款月'].sum() == 4          # 2020, 2021, 2022, 2023
    # Those two months before the first January are dropped, not paid out twice.
    assert run.index[0] > index[0]


def test_income_is_reported_by_calendar_year_and_only_when_the_year_is_whole():
    index = pd.date_range('2019-11-01', periods=40, freq='ME')
    growth = pd.Series([100.0] * 40, index=index)
    buffer = pd.Series([50.0] * 40, index=index)
    run = backtest(growth, buffer, 3000 * 10000, 0.9)
    paid = yearly_income(run)
    # The run ends in February 2023, so that year is not a year yet and is left out.
    assert list(paid.index) == [2020, 2021, 2022]
    assert paid.loc[2020] == pytest.approx(run.loc['2020', '當月生活費'].sum())


def test_a_history_with_no_january_at_all_is_still_refused():
    index = pd.date_range('2020-02-01', periods=10, freq='ME')
    flat = pd.Series([100.0] * 10, index=index)
    with pytest.raises(ValueError):
        backtest(flat, flat, 3000 * 10000, 0.9)


def test_all_three_backtest_presets_are_the_same_rule_in_different_clothes():
    """退休6 and 退休7 exist to be 退休5 over a period long enough to look at. That only works
    if they differ from it in the growth pool and in nothing else -- same ratio, same buffer,
    same principal. Sharing the buffer is also what puts 6 and 7 on one window."""
    shapes = {name: PRESETS[name] for name in BACKTEST_PRESETS}
    buffers, ratios, amounts = set(), set(), set()
    for name, config in shapes.items():
        growth, buffer = backtest_holdings(name)
        assert config['weights'][growth] == 90.0, name
        assert config['weights'][buffer] == 10.0, name
        buffers.add(buffer)
        ratios.add(tuple(sorted(config['weights'].values())))
        amounts.add(config['amount_wan'])
    assert len(buffers) == 1, f'緩衝池不同就落不到同一段期間：{buffers}'
    assert len(ratios) == 1 and len(amounts) == 1


def test_every_offered_preset_says_what_picking_it_means():
    """The numbers under the chart change completely with the choice; an unlabelled option
    would leave a reader comparing two things without being told what they are."""
    for name in BACKTEST_PRESETS:
        assert BACKTEST_NOTES.get(name), name
    assert BACKTEST_DEFAULT in BACKTEST_PRESETS


def test_the_taiwan_preset_is_flagged_for_what_the_window_cannot_show():
    """退休7 wins on this sample by a wide margin, and the sample is a TSMC/AI supercycle.
    Shipping the number without that beside it would read as a recommendation."""
    note = BACKTEST_NOTES['退休7']
    assert '台積電' in note
    assert '不是可以外推' in note or '外推' in note


def test_the_share_follows_whichever_preset_is_being_run():
    for name in BACKTEST_PRESETS:
        weights = PRESETS[name]['weights']
        assert growth_share(PRESET, name) == pytest.approx(
            max(weights.values()) / sum(weights.values()))
    # The original ratio is a property of the design, not of any preset's weights.
    assert growth_share(ORIGINAL, '退休7') == pytest.approx(100 / 112)


def test_a_faster_growth_pool_leaves_a_thinner_buffer():
    """The page says the buffer settles near a tenth. It does at the return gap that algebra
    was solved for -- 退休7 ends at 5.7% against 退休6's 9.7% on the same window. So "stays at
    a tenth" is a result of those returns, not something the rule guarantees."""
    slow_g, slow_b = _flat(months=85, growth_step=0.005)
    fast_g, fast_b = _flat(months=85, growth_step=0.012)
    slow = backtest(slow_g, slow_b, 3000 * 10000, 0.9)
    fast = backtest(fast_g, fast_b, 3000 * 10000, 0.9)

    def ending_share(run):
        return run['緩衝池'].iloc[-1] / run['總資產'].iloc[-1]

    assert ending_share(fast) < ending_share(slow)
    assert ending_share(slow) < 0.9, 'sanity: the buffer is the small pool'


def _series(months, start='2020-01-01', step=0.004, base=100.0):
    index = pd.date_range(start, periods=months, freq='ME')
    return pd.Series([base * (1 + step) ** i for i in range(months)], index=index)


def test_the_shared_window_is_the_overlap_not_the_union():
    prices = {'退休6': (_series(60), _series(60, base=50, step=0.001)),
              '退休7': (_series(40, start='2021-01-01'),
                        _series(40, start='2021-01-01', base=50, step=0.001))}
    window = shared_window(prices)
    assert window is not None
    assert window[0] == pd.Timestamp('2021-01-31')
    assert window[-1] == pd.Timestamp('2024-04-30')


def test_a_preset_too_short_to_run_does_not_drag_the_others_down_with_it():
    """退休5 has a few weeks. Intersecting first would shrink the shared window to those
    weeks and every preset would then fail -- a comparison of nothing against nothing."""
    long_g, long_b = _series(85), _series(85, base=50, step=0.001)
    prices = {'退休6': (long_g, long_b),
              '退休7': (_series(85, step=0.008), long_b),
              '退休5': (_series(3, start='2026-07-01'), long_b)}
    frame, window = compare_presets(prices, 3000 * 10000, 0.9)
    assert list(frame.index) == ['退休6', '退休7']
    assert window is not None and (window[1] - window[0]).days > 365 * 5


def test_every_compared_preset_is_run_over_the_same_window():
    """Otherwise the one holding the youngest fund is rewarded for having less history."""
    shared_b = _series(85, base=50, step=0.001)
    prices = {'退休6': (_series(85), shared_b),
              '退休7': (_series(100, start='2017-01-01', step=0.008), shared_b)}
    frame, window = compare_presets(prices, 3000 * 10000, 0.9)
    assert len(frame) == 2
    # Same principal, same first transfer, so the first year has to be identical.
    assert frame.loc['退休6', '首年生活費'] == pytest.approx(frame.loc['退休7', '首年生活費'])
    assert frame.loc['退休6', '末年'] == frame.loc['退休7', '末年']


def test_the_window_reported_is_the_one_the_runs_cover():
    """The data overlap starts in November; the runs start at the first January. Quoting
    the former would name months nobody ran."""
    november = _series(40, start='2019-11-01')
    prices = {'退休6': (november, _series(40, start='2019-11-01', base=50, step=0.001)),
              '退休7': (_series(40, start='2019-11-01', step=0.008),
                        _series(40, start='2019-11-01', base=50, step=0.001))}
    frame, window = compare_presets(prices, 3000 * 10000, 0.9)
    assert len(frame) == 2
    assert window[0].month == 1 and window[0].year == 2020


def test_nothing_to_compare_returns_nothing_rather_than_one_lonely_column():
    short = _series(3, start='2026-07-01')
    frame, window = compare_presets({'退休5': (short, short)}, 3000 * 10000, 0.9)
    assert frame.empty and window is None


def test_a_faster_growth_pool_reads_across_the_row_as_a_trade_not_a_win():
    """The column that wins on income is the column that loses on drawdown. If that ever
    stops being true the table is no longer showing a trade-off and the caption lies."""
    shared_b = _series(85, base=50, step=0.001)
    prices = {'退休6': (_series(85, step=0.003), shared_b),
              '退休7': (_series(85, step=0.010), shared_b)}
    frame, _ = compare_presets(prices, 3000 * 10000, 0.9)
    assert frame.loc['退休7', '期末總資產'] > frame.loc['退休6', '期末總資產']
    assert frame.loc['退休7', '期末緩衝池佔比'] < frame.loc['退休6', '期末緩衝池佔比']
