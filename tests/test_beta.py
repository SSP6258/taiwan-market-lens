import numpy as np
import pandas as pd
import pytest
from beta_analysis import fit_beta


def fixture():
    x = np.random.default_rng(42).normal(0, .01, 80)
    dates = pd.bdate_range('2025-01-01', periods=81)
    return (pd.Series(100*np.cumprod(np.r_[1,1+.001+1.5*x]),index=dates),
            pd.Series(100*np.cumprod(np.r_[1,1+x]),index=dates))


def test_known_beta_intercept_and_r_squared():
    a,b = fixture()
    beta, intercept, r2, pairs = fit_beta(a,b)
    assert beta == pytest.approx(1.5)
    assert intercept == pytest.approx(.001)
    assert r2 == pytest.approx(1)
    assert len(pairs) == 80


def test_missing_data_and_constant_benchmark():
    a,b = fixture()
    a.iloc[30] = np.nan
    _,_,_,pairs = fit_beta(a,b)
    assert a.index[30] not in pairs.index
    assert a.index[31] not in pairs.index
    with pytest.raises(ValueError, match='波動為零'):
        fit_beta(a,b*0+100)
    with pytest.raises(ValueError, match='至少需要'):
        fit_beta(a.iloc[:10], b.iloc[:10])
