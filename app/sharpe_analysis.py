"""Comparable Sharpe estimates from a shared complete price segment."""
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from correlation import analysis_data

UI_VERSION = 3
# Tall enough that Vega never culls alternate axis labels on a horizontal bar chart.
ROW_HEIGHT = 44


def sharpe_stats(segment, weights, annual_rate):
    daily = segment.pct_change(fill_method=None).iloc[1:]
    if weights is not None:
        nav = segment.div(segment.iloc[0]).mul(weights, axis=1).sum(axis=1)
        daily = daily.assign(組合=nav.pct_change(fill_method=None).iloc[1:])
    excess = daily - ((1 + annual_rate / 100) ** (1 / 252) - 1)
    vol = excess.std(ddof=1)
    return pd.DataFrame({'夏普比率': excess.mean().div(vol.where(vol > 1e-12)) * np.sqrt(252),
                         '年化平均超額報酬 (%)': excess.mean() * 25200,
                         '年化波動 (%)': vol * np.sqrt(252) * 100,
                         '日報酬筆數': daily.count()})


@st.fragment
def render_sharpe(prices, label, basis, weights, portfolio_name):
    st.subheader('報酬與波動的交換效率')
    st.write('每承受一單位波動，換到多少超過無風險利率的平均報酬？')
    rate = st.number_input('無風險年利率假設 (%)', min_value=0., max_value=20., value=2., step=.1, format='%.1f', key='sharpe_rate', help='可調整的固定年有效利率假設，預設 2.0% 並非即時市場利率。比較各配置時請使用相同假設。')
    _, _, segment = analysis_data(prices)
    if len(segment) < 21:
        st.info('至少需要 20 筆共同日報酬，才顯示夏普分析。請延長比較區間。')
        return
    valid_weights = weights if set(weights.index) == set(segment.columns) else None
    if valid_weights is None:
        st.warning('部分標的缺資料，暫停組合計算；不自動重新分配權重。')
    result = sharpe_stats(segment, valid_weights, rate)
    st.caption(f'共同試算期間 {segment.index[0]:%Y/%m/%d} — {segment.index[-1]:%Y/%m/%d} · {len(segment)-1} 筆日報酬')
    if len(segment) < 253:
        st.caption('樣本不足一年；以下是短期間日報酬年化估計，可能受少數漲跌影響，不能視為穩定的長期表現。')
    if not basis.startswith('還原'):
        st.warning('目前使用未還原收盤價，未含現金配息，除息或分割跳空可能影響夏普比率。')
    if valid_weights is not None:
        v = result.loc['組合','夏普比率']
        st.metric(portfolio_name + ' · 夏普比率', '—' if pd.isna(v) else f'{v:.1f}', border=True)
        st.caption('沿用側邊欄權重，起初投入後持有、不再平衡；由組合每日報酬重新計算，並非各檔夏普的加權平均。')
    result['類型'] = ['目前配置組合' if s == '組合' else ('個別標的（正值）' if result.loc[s,'夏普比率'] >= 0 else '個別標的（負值）') for s in result.index]
    result.index = [portfolio_name if s == '組合' else label(s) for s in result.index]
    chart_data = result.rename_axis('標的').reset_index().dropna(subset=['夏普比率'])
    chart = alt.Chart(chart_data).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y('標的:N',sort='-x',title=None,axis=alt.Axis(labelLimit=260,labelOverlap=False)),
        x=alt.X('夏普比率:Q',title='夏普比率',axis=alt.Axis(format='.1f')),
        color=alt.Color('類型:N', scale=alt.Scale(domain=['目前配置組合','個別標的（正值）','個別標的（負值）'], range=['#F5C451','#35CDBF','#FF7285']), legend=alt.Legend(orient='bottom', title=None)),
        tooltip=['標的:N',alt.Tooltip('夏普比率:Q',format='.1f'),alt.Tooltip('年化波動 (%):Q',format='.1f')])
    zero = alt.Chart(pd.DataFrame({'零':[0]})).mark_rule(color='#94A3B8').encode(x=alt.X('零:Q',title='夏普比率'))
    st.altair_chart((chart + zero).properties(height=max(240,len(chart_data)*ROW_HEIGHT)),width='stretch')
    result = result.drop(columns='類型')
    st.dataframe(result, column_config={c:st.column_config.NumberColumn(format='%d' if c=='日報酬筆數' else '%.1f') for c in result},width='stretch')
    st.markdown("""**如何解讀**
- 正值：平均報酬超過無風險假設；接近零：超額報酬很少；負值：低於無風險假設，不一定是虧損。
- 在相同期間及假設下，正夏普較高代表報酬相對波動的效率較高，不代表賺最多。負值時不宜單靠排名決策，增加波動反而可能讓負夏普更接近零。
- 「—」代表波動接近零，無法合理估計；不是零分。

**如何運用**
1. 記下目前組合的夏普、報酬及最大回撤，再修改側邊欄權重比較。
2. 使用相同區間與無風險利率；改看不同市場階段，確認結論是否穩定。
3. 不要反覆調權重只追求歷史最高夏普，可能過度迎合這段行情；較高夏普不代表最適合你的目標。
4. 搭配最大回撤評估承受能力，搭配每月配息評估生活費來源；夏普無法說明配息是否穩定。

**計算與限制**
採各檔共同的最長連續完整行情區段，不補缺值。每日超額報酬＝每日報酬 − [(1＋年利率)^(1/252)−1]；夏普＝每日超額報酬平均 ÷ 樣本標準差 × √252。年化平均超額報酬為算術平均年化，不是複合年化報酬率。年化假設忽略報酬自相關。

上下波動都計入風險，無法充分描述暴跌、流動性及尾端風險。未計交易費稅，歷史高夏普不保證未來。無固定門檻可保證配置適合你。
""")
