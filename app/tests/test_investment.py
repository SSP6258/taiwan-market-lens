import pandas as pd
import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from investment import cash_result, repair_distribution_units


def test_cash_excludes_buy_day_and_does_not_double_count():
    index=pd.to_datetime(['2024-01-01','2025-01-01','2025-02-01','2025-03-01'])
    h=pd.DataFrame({'Close':[100,100,95,110],'Dividends':[0,8,5,0],'Stock Splits':[0,0,0,0]},index=index)
    result,events=cash_result({'A':h},pd.Series({'A':1.}),1000,index[1],index[-1])
    assert result.iloc[0]['期間除息金額']==50
    assert result.iloc[0]['含息損益']==150
    assert result.iloc[0]['期間成本配息率 (%)']==5
    assert len(events)==1
    assert events.iloc[0]["當次配息殖利率 (%)"] == pytest.approx(5.0)


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
        filled=AppTest.from_string(script.replace('AMOUNT','1000.')).run(timeout=15)
        assert not filled.exception
        assert len(filled.metric)==4
        assert filled.metric[0].value=="+10.0%"
        assert filled.metric[2].value=='NT$ 1,100'
        fetch.assert_not_called()


def test_monthly_weights_drift_and_actual_month_end():
    from investment import monthly_weights
    dates = pd.to_datetime(['2025-01-15','2025-01-31','2025-02-10'])
    prices = pd.DataFrame({'A':[100.,200.,300.], 'B':[100.,100.,100.], 'C':[10.,20.,30.]}, index=dates)
    result = monthly_weights(prices, pd.Series({'A':.5,'B':.5,'C':0.}))
    assert result.groupby('月份')['占比'].sum().tolist() == pytest.approx([1.,1.])
    assert result.loc[result['代碼']=='A','占比'].tolist() == pytest.approx([2/3,.75])
    assert set(result['日期']) == {'2025/01/31','2025/02/10'}
    assert result['端點'].all()
    one = monthly_weights(prices.iloc[:2], pd.Series({'A':.5,'B':.5,'C':0.}))
    assert len(one) == 3
    assert one['端點'].all()


def test_money_cards_carry_the_wan_reading():
    """Eight digits are hard to size up at a glance; the 萬 line under the value is
    what a reader actually compares against the amount they typed in the sidebar."""
    script = '''import pandas as pd
from investment import render_investment
p=pd.DataFrame({'A':[100.,105.,110.]},index=pd.bdate_range('2025-01-01',periods=3))
render_investment(p,pd.Series({'A':1.}),30000000.,str,'還原價格')
'''
    app = AppTest.from_string(script).run(timeout=15)
    assert not app.exception
    assert app.metric[2].value == 'NT$ 33,000,000'
    assert app.metric[2].delta == '3,300 萬'
    # The return percentage is not an amount; its second line is the window it covers.
    assert app.metric[0].delta == '2025/01/01 — 2025/01/03'


def test_a_distribution_left_in_the_old_unit_is_brought_back():
    """0050's prices changed unit on 2014-01-02 and its dividends only a year later, so one
    ex-date sits in the old unit beside a new-unit price and reads as a 9.5% distribution."""
    index = pd.bdate_range('2024-01-01', periods=6)
    h = pd.DataFrame({'Close': [16.0] * 6, 'Dividends': [0, 0, 1.55, 0, 0, 0.4],
                      'Stock Splits': [0.0] * 6}, index=index)
    h.attrs['unit_breaks'] = [(index[0], 4)]
    repaired = repair_distribution_units(h)
    assert repaired['Dividends'].iloc[2] == pytest.approx(1.55 / 4)
    # The plausible one beside it is published as it stands.
    assert repaired['Dividends'].iloc[5] == pytest.approx(0.4)


def test_a_large_distribution_without_a_split_is_published_as_it_stands():
    index = pd.bdate_range('2024-01-01', periods=4)
    h = pd.DataFrame({'Close': [16.0] * 4, 'Dividends': [0, 1.55, 0, 0],
                      'Stock Splits': [0.0] * 4}, index=index)
    assert repair_distribution_units(h)['Dividends'].tolist() == [0, 1.55, 0, 0]


def test_both_edges_of_a_chart_carry_numbers():
    # Measured while building this: a right-hand `orient` on its own MOVES the numbers.
    # Layered charts merge axes that share a scale, so the two collapse back into one
    # and the chart is left with numbers down the right only -- no exception, nothing
    # missing from the page, just a chart that quietly lost half of what it had.
    import altair as alt
    from investment import with_right_edge_numbers
    frame = pd.DataFrame({'v': [.25, .75]})
    scale = alt.Scale(domain=[0, 1])
    bars = alt.Chart(frame).mark_bar().encode(
        y=alt.Y('v:Q', title='占比', scale=scale, axis=alt.Axis(format='.0%')))
    spec = with_right_edge_numbers(bars, frame, alt.Y(
        'v:Q', title=None, scale=scale, axis=alt.Axis(format='.0%', orient='right'))).to_dict()
    assert spec['resolve']['axis']['y'] == 'independent'
    drawn = [l['encoding']['y'] for l in spec['layer'] if l['encoding']['y'].get('axis') is not None]
    assert sorted(y['axis'].get('orient', 'left') for y in drawn) == ['left', 'right']
    # Both sides must read off one scale, or the two edges of one chart disagree.
    assert {tuple(y['scale']['domain']) for y in drawn} == {(0, 1)}


def test_the_added_layer_draws_nothing_of_its_own():
    # It exists to carry an axis. A visible rule on every row would stripe the chart.
    import altair as alt
    from investment import with_right_edge_numbers
    frame = pd.DataFrame({'v': [1., 2.]})
    base = alt.Chart(frame).mark_line().encode(y=alt.Y('v:Q'))
    added = with_right_edge_numbers(base, frame, alt.Y('v:Q', axis=alt.Axis(orient='right')))
    assert added.to_dict()['layer'][-1]['mark']['opacity'] == 0


def test_the_investment_page_still_draws_both_of_its_charts():
    # 第六十次: a chart line got eaten by a splice and the page rendered anyway -- cards,
    # captions and no exception, just no chart. Counting them is the only way to see it.
    import json
    script = 'import pandas as pd, numpy as np\n' \
             'from investment import render_investment\n' \
             "idx = pd.bdate_range('2023-01-02', periods=300)\n" \
             'rng = np.random.default_rng(7)\n' \
             "p = pd.DataFrame(100*np.cumprod(1+rng.normal(.0006,.011,(len(idx),2)),axis=0), index=idx, columns=['A','B'])\n" \
             "render_investment(p, pd.Series({'A':.6,'B':.4}), 1e7, str, '還原價格')\n"
    with patch('investment.load_distributions') as fetch:
        app = AppTest.from_string(script).run(timeout=30)
        assert not app.exception
        charts = list(app.get('vega_lite_chart'))
        assert len(charts) == 2, '資產價值與占比追蹤兩張圖都要在'
        for chart in charts:
            spec = chart.spec if isinstance(chart.spec, dict) else json.loads(chart.spec)
            assert spec['resolve']['axis']['y'] == 'independent'
        fetch.assert_not_called()
