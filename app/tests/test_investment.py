import pandas as pd
import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from investment import cash_result


def test_cash_excludes_buy_day_and_does_not_double_count():
    index=pd.to_datetime(['2024-01-01','2025-01-01','2025-02-01','2025-03-01'])
    h=pd.DataFrame({'Close':[100,100,95,110],'Dividends':[0,8,5,0],'Stock Splits':[0,0,0,0]},index=index)
    result,events=cash_result({'A':h},pd.Series({'A':1.}),1000,index[1],index[-1])
    assert result.iloc[0]['期間除息金額']==50
    assert result.iloc[0]['含息損益']==150
    assert result.iloc[0]['期間成本配息率 (%)']==5
    assert len(events)==1


def test_split_adjusted_units_not_split_twice():
    index=pd.bdate_range('2025-01-01',periods=3)
    h=pd.DataFrame({'Close':[50,50,55],'Dividends':[0,1,0],'Stock Splits':[0,2,0]},index=index)
    result,_=cash_result({'A':h},pd.Series({'A':1.}),1000,index[0],index[-1])
    assert result.iloc[0]['期末市值']==1100
    assert result.iloc[0]['期間除息金額']==20


def test_amount_does_not_fetch_distributions_until_enabled():
    script='''import pandas as pd
from investment import render_investment
p=pd.DataFrame({'A':[100.,105.,110.]},index=pd.bdate_range('2025-01-01',periods=3))
render_investment(p,pd.Series({'A':1.}),AMOUNT,str,'還原價格')
'''
    with patch('investment.load_distributions') as fetch:
        empty=AppTest.from_string(script.replace('AMOUNT','None')).run()
        assert not empty.metric
        filled=AppTest.from_string(script.replace('AMOUNT','1000.')).run()
        assert not filled.exception
        assert len(filled.metric)==3
        assert filled.metric[1].value=='NT$ 1,100'
        fetch.assert_not_called()
