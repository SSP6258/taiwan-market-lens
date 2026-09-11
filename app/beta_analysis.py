"""Pairwise daily-return market sensitivity, with intercept."""

# Shared with the other horizontal bar charts so axis labels are never dropped.
ROW_HEIGHT = 44
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from market import load_symbol


def fit_beta(asset, benchmark):
    prices = pd.concat({'標的': asset, '基準': benchmark}, axis=1).sort_index()
    prices = prices.replace([np.inf, -np.inf], np.nan).where(prices > 0)
    pairs = prices.pct_change(fill_method=None).dropna()
    if len(pairs) < 20:
        raise ValueError(f'共同有效日報酬僅 {len(pairs)} 筆，至少需要 20 筆。')
    x, y = pairs['基準'], pairs['標的']
    if x.var() <= 1e-16:
        raise ValueError('基準波動為零，無法估計 Beta。')
    beta = x.cov(y) / x.var()
    intercept = y.mean() - beta*x.mean()
    r2 = x.corr(y)**2 if y.var() > 1e-16 else np.nan
    return beta, intercept, r2, pairs


def render_beta(prices, label, names, start, end, basis, weights=None, portfolio_name='等權重組合'):
    st.subheader('對市場漲跌，有多敏感？')
    st.caption('BETA LAB · 每日報酬回歸分析')
    benchmark_label = lambda s: '台灣加權指數（大盤）· ^TWII' if s == '^TWII' else label(s)
    options = list(dict.fromkeys(['0050.TW', '^TWII'] + list(prices.columns) + list(names)))
    benchmark = st.selectbox('比較基準', options, format_func=benchmark_label, key='beta_benchmark')
    st.caption('基準獨立於選股清單，不占 12 檔名額。0050 是台股 ETF 代理基準，不是加權指數本身。')
    try:
        if benchmark in prices:
            reference = prices[benchmark]
        else:
            with st.spinner('正在取得基準行情…'):
                history, _ = load_symbol(benchmark, start, end)
            reference = history['Close' if benchmark == '^TWII' else ('Adj Close' if basis.startswith('還原') else 'Close')]
    except Exception:
        st.warning('無法取得基準行情，請更換基準或稍後重試。')
        return
    if benchmark == '^TWII':
        st.info('大盤基準採加權價格指數收盤值，不含股息再投資。標的仍使用目前選擇的價格基準；若採還原價格，兩者的配息處理不同。')
    source_label = label
    label = lambda s: portfolio_name if s == '__portfolio__' else source_label(s)
    prices = prices.copy()
    if weights is not None:
        if set(weights.index) != set(prices.columns):
            st.warning('部分配置標的行情缺失，暫不計算組合 Beta；單檔分析仍可使用。')
        else:
            from correlation import analysis_data
            _, _, segment = analysis_data(prices)
            if len(segment) >= 21:
                portfolio = (segment / segment.iloc[0]).mul(weights, axis=1).sum(axis=1)
                prices['__portfolio__'] = portfolio.reindex(prices.index)
                st.caption('組合採側邊欄起始配置，持有不再平衡；使用與分散效果相同的最長完整區段，再對齊基準。')
                st.caption('目前配置：' + '、'.join(f'{source_label(s)} {weights[s]*100:.1f}%' for s in weights.index))
            else:
                st.info('完整行情區段不足，暫無法計算組合 Beta。')
    rows, fits = [], {}
    for symbol in prices:
        if symbol == benchmark:
            continue
        try:
            beta, intercept, r2, pairs = fit_beta(prices[symbol], reference)
            fits[symbol] = (beta, intercept, r2, pairs)
            rows.append({'標的':label(symbol), 'Beta':beta, 'R²':r2, '樣本數':len(pairs), '起日':pairs.index[0].strftime('%Y/%m/%d'), '迄日':pairs.index[-1].strftime('%Y/%m/%d')})
        except ValueError as exc:
            st.warning(f'{label(symbol)}：{exc}')
    if not rows:
        st.info('請選擇至少一檔與基準不同、且有足夠資料的標的。')
        return
    frame = pd.DataFrame(rows).sort_values('Beta', ascending=False)
    st.write('Beta 1.0 代表對基準的敏感度相近；大於 1.0 較敏感，介於 0.0 與 1.0 較低，負值表示反向關係。這是歷史統計，不是單日預測。')
    with st.container(border=True):
        st.subheader('敏感度排序')
        bars = alt.Chart(frame).mark_bar(cornerRadiusEnd=4).encode(y=alt.Y('標的:N', sort='-x', title=None, axis=alt.Axis(labelLimit=260, labelOverlap=False)), x=alt.X('Beta:Q'), color=alt.condition(alt.datum.Beta < 0, alt.value('#F3A65A'), alt.value('#35CDBF')), tooltip=['標的:N',alt.Tooltip('Beta:Q',format='.2f'),alt.Tooltip('R²:Q',format='.2f'),'樣本數:Q','起日:N','迄日:N'])
        rule = alt.Chart(pd.DataFrame({'Beta':[1.0]})).mark_rule(color='#F3C969',strokeDash=[5,4]).encode(x='Beta:Q')
        st.altair_chart((bars+rule).properties(height=max(240,len(rows)*ROW_HEIGHT)), width='stretch')
        st.caption(f'金色虛線：Beta 1.0 · 基準：{benchmark_label(benchmark)} · {basis}。每檔各自對齊基準，樣本期間可能不同。')
        st.dataframe(frame, hide_index=True, column_config={'Beta':st.column_config.NumberColumn(format='%.2f'), 'R²':st.column_config.NumberColumn(format='%.2f')}, width='stretch')
    with st.container(border=True):
        st.subheader('報酬散點與回歸線')
        symbol = st.selectbox('查看標的', list(fits), format_func=label, key='beta_asset')
        beta, intercept, r2, pairs = fits[symbol]
        for card, title, value in zip(st.columns(3), ['Beta','R²','共同樣本'],[f'{beta:.2f}',f'{r2:.2f}' if pd.notna(r2) else '無法估計',str(len(pairs))]):
            card.metric(title,value)
        x_title = f'{benchmark_label(benchmark)} 每日報酬 (%)'
        y_title = f'{label(symbol)} 每日報酬 (%)'
        plot = (pairs*100).rename_axis('日期').reset_index()
        points = alt.Chart(plot).mark_circle(size=40,opacity=.55,color='#35CDBF').encode(x=alt.X('基準:Q',title=x_title),y=alt.Y('標的:Q',title=y_title),tooltip=[alt.Tooltip('日期:T',format='%Y/%m/%d'),alt.Tooltip('基準:Q',format='.1f'),alt.Tooltip('標的:Q',format='.1f')])
        x = np.array([pairs['基準'].min(), pairs['基準'].max()])
        line = alt.Chart(pd.DataFrame({'基準':x*100,'標的':(intercept+beta*x)*100})).mark_line(color='#F3C969',strokeWidth=2).encode(x=alt.X('基準:Q', title=x_title),y=alt.Y('標的:Q', title=y_title))
        st.altair_chart((points+line).properties(height=300),width='stretch')
        st.caption(f'{pairs.index[0]:%Y/%m/%d} — {pairs.index[-1]:%Y/%m/%d} · 每個點是一筆共同有效日報酬，金線為含截距的最小平方法回歸。')
        if pd.notna(r2):
            st.write(f'本期間，基準的線性模型可解釋約 {r2*100:.1f}% 的標的日報酬變異。R² 低時，單靠 Beta 描述風險並不充分。')
        if len(pairs) < 60:
            st.warning('樣本不足 60 筆，估計可能不穩定。')
    with st.expander('計算方式與解讀限制'):
        st.write('Beta＝標的與基準日報酬的樣本共變異數 ÷ 基準日報酬的樣本變異數。R² 為相關係數平方；零波動標的的 R² 不定義。先在日期聯集算日報酬，再排除缺漏，不補值。Beta 與 R² 保留兩位小數。')
        st.write('海外股票、債券及黃金 ETF 對 0050 的低 Beta，不代表低風險。不同市場收盤時間、匯率與交易日差異都可能影響結果；此分析不估計因果或未來績效。')
