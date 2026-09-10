import numpy as np
import pandas as pd
import pytest
from sharpe_analysis import sharpe_stats
from streamlit.testing.v1 import AppTest


def test_sharpe_uses_daily_excess_and_portfolio_returns():
    p = pd.DataFrame({'A':[100.,110.,99.,120.], 'B':[100.,98.,105.,108.], 'Flat':[100.]*4})
    w = pd.Series({'A':.7,'B':.3,'Flat':0.})
    result = sharpe_stats(p,w,2.)
    nav = .7*p.A/100 + .3*p.B/100
    excess = nav.pct_change().dropna() - (1.02**(1/252)-1)
    assert result.loc['組合','夏普比率'] == pytest.approx(excess.mean()/excess.std(ddof=1)*np.sqrt(252))
    assert np.isnan(result.loc['Flat','夏普比率'])
    assert '組合' not in sharpe_stats(p,None,2.).index


def test_sharpe_page_renders():
    app = AppTest.from_string("""import pandas as pd
import numpy as np
from sharpe_analysis import render_sharpe
p=pd.DataFrame({'A':100*np.cumprod(1+np.sin(np.arange(30))*.01)},index=pd.bdate_range('2025-01-01',periods=30))
render_sharpe(p,str,'還原價格',pd.Series({'A':1.}),'自訂組合')
""").run(timeout=20)
    assert not app.exception
    assert len(app.metric)==1
    app.number_input[0].set_value(3.).run(timeout=20)
    assert not app.exception
