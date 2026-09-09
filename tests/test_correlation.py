import numpy as np
import pandas as pd
from correlation import analysis_data


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
