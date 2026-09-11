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
