from datetime import date
from math import factorial

import numpy as np
import pandas as pd
import pytest

from retirement_strategy import backtest
from sequence_risk import (EXACT_UP_TO, MIN_YEARS, ORIGINAL, book_orders, buffer_rule,
                           complete_years, configuration_returns, every_order,
                           fixed_withdrawal, ranking, start_years)

TODAY = date(2026, 11, 12)


def _daily(start, end, growth=0.0):
    index = pd.bdate_range(start, end)
    return pd.Series(100 * (1 + growth) ** np.arange(len(index)), index=index)


def test_only_whole_years_before_this_one_count():
    """A year needs its December and a base: last year's close, or its own first days."""
    years = complete_years(_daily('2019-01-02', '2026-11-11'), TODAY)
    assert list(years.index) == list(range(2019, 2026))
    # Opening in March leaves that year without a base, so it is not counted.
    assert list(complete_years(_daily('2019-03-04', '2022-12-30'), TODAY).index) == [2020, 2021, 2022]
    # Ending in November leaves the year unfinished.
    assert 2022 not in complete_years(_daily('2019-01-02', '2022-11-15'), TODAY).index


def test_a_configuration_short_of_whole_years_is_left_out_and_says_why():
    histories = {'A': _daily('2010-01-04', '2026-11-11'), 'B': _daily('2024-06-03', '2026-11-11')}
    weights = pd.Series({'A': .5, 'B': .5})
    frame, why = configuration_returns(histories, weights, TODAY)
    assert frame is None and 'B' in why and f'門檻 {MIN_YEARS} 年' in why
    frame, why = configuration_returns(histories, pd.Series({'A': 1.0}), TODAY)
    assert why is None and len(frame) == 16


def test_the_books_four_orders():
    blended = np.array([.1, -.2, .3, -.1, .05])
    orders = book_orders(blended)
    assert list(orders[ORIGINAL]) == [0, 1, 2, 3, 4]
    assert list(orders['反轉順序']) == [4, 3, 2, 1, 0]
    # Losses and gains each keep their original order, as the book does.
    assert list(orders['負報酬在前']) == [1, 3, 0, 2, 4]
    assert list(orders['負報酬在後']) == [0, 2, 4, 1, 3]


def test_every_order_is_run_once_and_history_is_the_first():
    orders, exact = every_order(6)
    assert exact and len(orders) == factorial(6) == len({tuple(o) for o in orders})
    assert list(orders[0]) == list(range(6))
    sampled, exact = every_order(EXACT_UP_TO + 1, samples=50)
    assert not exact and list(sampled[0]) == list(range(EXACT_UP_TO + 1))
    assert all(sorted(o) == list(range(EXACT_UP_TO + 1)) for o in sampled)


def test_without_withdrawals_the_order_changes_nothing():
    """The whole case for the measure: any spread it shows comes from withdrawing."""
    returns = np.array([[.3, .02], [-.25, .01], [.1, .03], [-.05, .0], [.2, .02], [.15, .01]])
    orders, _ = every_order(6)
    totals, dry = fixed_withdrawal(returns, [.9, .1], 1000.0, 0.0, orders)
    assert np.allclose(totals[:, -1], totals[0, -1])
    totals, _ = fixed_withdrawal(returns, [.9, .1], 1000.0, 40.0, orders)
    assert totals[:, -1].max() / totals[:, -1].min() > 1.05


def test_a_fixed_withdrawal_by_hand_and_the_year_it_runs_dry():
    totals, dry = fixed_withdrawal(np.array([[.1], [.0]]), [1.0], 1000.0, 100.0, np.array([[0, 1]]))
    assert totals[0].tolist() == pytest.approx([1000, 990, 890])
    _, dry = fixed_withdrawal(np.array([[-.5], [-.5], [-.5]]), [1.0], 100.0, 40.0, np.array([[0, 1, 2]]))
    # 100, less 40, is 60, halved to 30: short of 40 when year 2 opens.
    assert dry[0] == 2


def test_the_buffer_rule_matches_backtest_exactly():
    """The vectorised loop must give backtest()'s own numbers on the same months."""
    returns = np.array([[.25, -.1, .02], [-.3, .05, .03], [.12, .2, .01], [.4, -.2, -.02]])
    steps = (1 + np.repeat(returns, 12, axis=0)) ** (1 / 12) - 1
    steps = np.vstack([np.zeros((1, 3)), steps])
    index = pd.date_range('2020-01-31', periods=len(steps), freq='ME')
    prices = pd.DataFrame(100 * np.cumprod(1 + steps, axis=0), index=index, columns=['a', 'b', 'buf'])
    run = backtest(prices[['a', 'b']], prices['buf'], 30_000_000, .9, growth_weights={'a': .5, 'b': .4})
    expected = run.loc[run['撥款月'], '年生活費'].to_numpy()[:len(returns)]
    income, totals = buffer_rule(returns, [.5, .4], 2, 30_000_000, .9, np.array([[0, 1, 2, 3]]))
    assert income[0] == pytest.approx(expected, rel=1e-12)
    assert totals[0, -1] == pytest.approx(run['總資產'].iloc[-2], rel=1e-12)


def test_the_ranking_puts_the_most_order_sensitive_first():
    years = list(range(2020, 2026))
    calm = pd.DataFrame({'X': [.05, .04, .06, .05, .05, .04]}, index=years)
    wild = pd.DataFrame({'Y': [.6, -.4, .5, -.3, .4, -.2]}, index=years)
    configs = {'平穩': pd.Series({'X': 1.0}), '劇烈': pd.Series({'Y': 1.0})}
    table, _ = ranking({'平穩': calm, '劇烈': wild}, configs, 30_000_000, .04)
    assert list(table['配置']) == ['劇烈', '平穩'] and list(table['排名']) == [1, 2]
    assert table.loc[1, '順序差距倍數'] < table.loc[0, '順序差距倍數']
    assert (table['排列數'] == factorial(6)).all()


def test_starting_years_run_in_the_order_they_happened():
    years = list(range(2009, 2026))
    frame = pd.DataFrame({'X': np.linspace(-.2, .3, len(years))}, index=years)
    starts = start_years(frame, pd.Series({'X': 1.0}), 1000.0, .04, horizon=10)
    assert list(starts['退休年']) == list(range(2009, 2017))
    assert starts['期間'].iloc[0] == '2009–2018'
