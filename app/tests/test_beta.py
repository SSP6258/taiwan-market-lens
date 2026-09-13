import numpy as np
import pandas as pd
import pytest
from beta_analysis import fit_beta
from streamlit.testing.v1 import AppTest


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


def test_a_benchmark_in_another_time_zone_is_flagged():
    """VT scores Beta 0.02 against 0050 on matching dates and 0.33 once the US day is moved
    to the next Taiwan one. The number stays as measured; the page says why it is small."""
    script = """
import pandas as pd, numpy as np
import streamlit as st
from beta_analysis import render_beta
rng = np.random.default_rng(3)
idx = pd.bdate_range('2025-01-01', periods=120)
p = pd.DataFrame({'0050.TW': 100*np.cumprod(1+rng.normal(0,.01,120)),
                  'VT': 100*np.cumprod(1+rng.normal(0,.01,120))}, index=idx)
render_beta(p, str, list(p), idx[0].date(), idx[-1].date(), '收盤價')
"""
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception
    assert [w for w in app.warning if '不同時區' in w.value], '跨時區標的應該要有警語'
    assert [w for w in app.warning if '不代表兩者無關' in w.value]
