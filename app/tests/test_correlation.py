import numpy as np
import pandas as pd
from correlation import analysis_data, portfolio_stats


def test_daily_correlation_and_gaps():
    r = np.array([.01, -.02, .03, -.01, .02, -.03])
    prices = pd.DataFrame({'a':100*np.cumprod(np.r_[1,1+r]), 'b':100*np.cumprod(np.r_[1,1-r])})
    daily, corr, _ = analysis_data(prices)
    assert abs(corr.loc['a','b'] + 1) < 1e-10
    prices.loc[3,'b'] = np.nan
    daily, _, segment = analysis_data(prices)
    assert 3 not in daily.index and 4 not in daily.index
    assert len(segment) == 3


def test_constant_series_is_undefined():
    _, corr, _ = analysis_data(pd.DataFrame({'a':[100]*30,'b':range(100,130)}))
    assert corr['a'].isna().all()


def test_portfolio_stats_blend_sits_between_holdings():
    """A perfectly anti-correlated pair must blend to lower volatility than either leg."""
    r = np.array([.02,-.02,.03,-.03,.01,-.01]*5)
    segment = pd.DataFrame({'a':100*np.cumprod(np.r_[1,1+r]), 'b':100*np.cumprod(np.r_[1,1-r])})
    weights = pd.Series({'a':.5,'b':.5})
    portfolio, volatility, drawdown = portfolio_stats(segment, weights, '組合')
    assert volatility['組合'] < min(volatility['a'], volatility['b'])
    assert drawdown['組合'] >= max(drawdown['a'], drawdown['b'])
    assert abs(portfolio.iloc[0] - 1) < 1e-12


def test_portfolio_stats_honours_uneven_weights():
    segment = pd.DataFrame({'a':[100.,110.,121.], 'b':[100.,100.,100.]})
    portfolio, _, _ = portfolio_stats(segment, pd.Series({'a':.8,'b':.2}), '組合')
    assert abs(portfolio.iloc[-1] - (.8*1.21 + .2)) < 1e-12


def _two_holdings():
    index = pd.date_range('2026-01-01', periods=4, freq='D')
    return pd.DataFrame({'a': [100., 110., 99., 121.], 'b': [100., 90., 99., 110.]}, index=index)


def test_blend_is_drawn_on_the_same_basis_as_each_holding():
    """Everything on the chart must share one starting day and one definition, or the
    blend would sit against its neighbours on a scale that is not theirs."""
    from correlation import blend_paths
    from market import compare_prices
    prices = _two_holdings()
    _, returns, drawdown, _ = compare_prices(prices)
    for held in ('a', 'b'):
        weights = pd.Series({'a': 1.0 if held == 'a' else 0.0, 'b': 0.0 if held == 'a' else 1.0})
        blend_return, blend_drawdown = blend_paths(prices, weights)
        # All of it in one holding is that holding, point for point.
        pd.testing.assert_series_equal(blend_return, returns[held], check_names=False)
        pd.testing.assert_series_equal(blend_drawdown, drawdown[held], check_names=False)


def test_blend_drawdown_is_not_the_average_of_the_drawdowns():
    """Taken per holding and averaged, this pair reads -10.0%; the blend never fell that
    far because they fell on different days. Averaging drawdowns is the classic error."""
    from correlation import blend_paths
    blend_return, blend_drawdown = blend_paths(_two_holdings(), pd.Series({'a': .5, 'b': .5}))
    assert list(blend_return.round(4)) == [0.0, 0.0, -1.0, 15.5]
    assert list(blend_drawdown.round(4)) == [0.0, 0.0, -1.0, 0.0]


def test_blend_never_leaves_the_range_of_its_holdings():
    """A weighted average of wealth paths cannot beat the best or trail the worst."""
    from correlation import blend_paths
    from market import compare_prices
    prices = _two_holdings()
    _, returns, _, _ = compare_prices(prices)
    blend_return, _ = blend_paths(prices, pd.Series({'a': .3, 'b': .7}))
    assert (blend_return >= returns.min(axis=1) - 1e-9).all()
    assert (blend_return <= returns.max(axis=1) + 1e-9).all()
