"""Daily-return correlation and a buy-and-hold diversification illustration."""
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st


def analysis_data(prices):
    clean = prices.sort_index().replace([np.inf, -np.inf], np.nan).where(prices > 0)
    daily = clean.pct_change(fill_method=None).dropna(how="any")
    corr = daily.corr().where(daily.std() > 1e-12, np.nan)
    corr.loc[daily.std() <= 1e-12, :] = np.nan
    # Portfolio uses a contiguous complete segment, never compounds across holes.
    complete = clean.notna().all(axis=1)
    groups = (~complete).cumsum()
    candidates = [g for _, g in clean[complete].groupby(groups[complete])]
    segment = max(candidates, key=len) if candidates else clean.iloc[:0]
    return daily, corr, segment


def portfolio_stats(segment, weights, portfolio_name='等權重組合'):
    """Wealth path, annualised volatility and max drawdown for each holding plus the blend."""
    wealth = segment / segment.iloc[0]
    portfolio = wealth.mul(weights, axis=1).sum(axis=1)
    wealth[portfolio_name] = portfolio
    volatility = wealth.pct_change(fill_method=None).iloc[1:].std() * np.sqrt(252) * 100
    drawdown = (wealth / wealth.cummax() - 1).min() * 100
    return portfolio, volatility, drawdown


def render_analysis(prices, label, basis, weights=None, portfolio_name='等權重組合'):
    st.subheader("一起漲跌，還是彼此分散？")
    st.caption("DIVERSIFICATION LAB · 每日報酬相關性與等權重持有試算")
    if prices.shape[1] < 2:
        st.info("請選擇至少兩檔標的，才能比較相關性與分散效果。")
        return
    daily, corr, segment = analysis_data(prices)
    if len(daily) < 20:
        st.info(f"目前只有 {len(daily)} 筆共同有效日報酬；至少需要 20 筆，請延長區間或移除資料較短的標的。")
        return
    st.caption(f"{daily.index[0]:%Y/%m/%d} — {daily.index[-1]:%Y/%m/%d} · {len(daily)} 筆共同日報酬 · {basis}")
    st.write("接近 +1：同向連動；接近 0：線性關係較弱；接近 −1：反向連動。低相關可能有助分散，但不保證下跌時能互相抵銷。")
    if len(daily) < 60:
        st.warning("樣本不足 60 筆，相關性可能不穩定；建議延長比較期間。")
    with st.container(border=True):
        st.subheader("相關性矩陣")
        codes = [s.split('.')[0] for s in corr.columns]
        records = [dict(x=a.split('.')[0], y=b.split('.')[0], 股票=label(a), 對照=label(b), 相關係數=corr.loc[a,b], 顯示=f"{corr.loc[a,b]:.2f}" if pd.notna(corr.loc[a,b]) else "—") for a in corr for b in corr]
        base = alt.Chart(pd.DataFrame(records)).encode(x=alt.X('x:N', sort=codes, title=None, axis=alt.Axis(labelAngle=-60, labelOverlap=False, labelFontSize=10, labelLimit=90, labelPadding=8)), y=alt.Y('y:N', sort=codes, title=None, axis=alt.Axis(labelOverlap=False, labelFontSize=11, labelLimit=90, labelPadding=8)), tooltip=['股票:N','對照:N',alt.Tooltip('相關係數:Q', format='.2f')])
        heat = base.mark_rect(cornerRadius=4, stroke='#0F172A', strokeWidth=3).encode(color=alt.Color('相關係數:Q', scale=alt.Scale(domain=[-1,0,1], range=['#22C9BB','#26364D','#F3A65A']), legend=alt.Legend(title='相關性', orient='bottom')))
        text = base.mark_text(fontSize=11, color='#F8FAFC').encode(text='顯示:N')
        st.altair_chart((heat + text).properties(height=max(260, len(codes)*34)).configure_view(stroke=None), width="stretch")
        st.caption("相關係數保留兩位小數。— 表示波動為零或無法估計。手機點選格子可查看完整名稱；亦可展開下方資料。")
        with st.expander("完整名稱與矩陣資料"):
            st.dataframe(corr.rename(index=label, columns=label).style.format('{:.2f}', na_rep='—'), width='stretch')

    with st.container(border=True):
        st.subheader("兩檔關係會不會改變？")
        left, right = st.columns(2)
        a = left.selectbox("標的 A", list(daily.columns), format_func=label, key='corr_a')
        b = right.selectbox("標的 B", [s for s in daily.columns if s != a], format_func=label, key='corr_b')
        if len(daily) >= 60:
            rolling = daily[a].rolling(60).corr(daily[b]).replace([np.inf,-np.inf],np.nan).dropna().rename('相關係數').rename_axis('日期').reset_index()
            chart = alt.Chart(rolling).mark_line(color='#35E0CE', strokeWidth=2.5).encode(x=alt.X('日期:T', title=None), y=alt.Y('相關係數:Q', title='相關係數', scale=alt.Scale(domain=[-1,1])), tooltip=[alt.Tooltip('日期:T', format='%Y/%m/%d'),alt.Tooltip('相關係數:Q',format='.2f')])
            zero = alt.Chart(pd.DataFrame({'零':[0]})).mark_rule(color='#64748B',strokeDash=[4,4]).encode(y=alt.Y('零:Q', title='相關係數'))
            st.altair_chart((chart+zero).properties(height=230), width='stretch')
            st.caption("虛線代表相關係數 0.0：接近虛線表示線性連動較弱，上方為正相關、下方為負相關；不代表兩檔完全獨立。每個點使用最近 60 筆共同有效日報酬；缺漏不補值，因此涵蓋的日曆期間可能不同。")
        else:
            st.info("滾動相關性需要至少 60 筆共同有效日報酬。")

    with st.container(border=True):
        st.subheader("搭配後，波動有減少嗎？")
        if len(segment) < 21:
            st.info("等權重試算需要至少 21 個連續完整的行情觀測日。")
            return
        if weights is None:
            weights = pd.Series(1 / len(segment.columns), index=segment.columns)
        if set(weights.index) != set(segment.columns):
            st.warning('部分標的行情缺失，暫停組合試算以保留原配置；請移除失敗標的或重新取得資料。')
            return
        st.caption('目前配置：' + '、'.join(f'{label(s)} {weights[s]*100:.1f}%' for s in weights.index))
        portfolio, volatility, drawdown = portfolio_stats(segment, weights, portfolio_name)
        st.caption(f"試算期間 {segment.index[0]:%Y/%m/%d} — {segment.index[-1]:%Y/%m/%d} · 採最長連續完整行情區段")
        st.write("依目前起始配置持有、不再平衡。未計交易成本與稅金；組合價值為各檔標準化價格依起始比重加權。")
        for card, title, value in zip(st.columns(3), ['組合區間報酬','組合年化波動','組合最大回撤'], [(portfolio.iloc[-1]-1)*100,volatility[portfolio_name],drawdown[portfolio_name]]):
            card.metric(title, f'{value:.1f}%')
        result = pd.DataFrame({'年化波動 (%)':volatility,'最大回撤 (%)':drawdown})
        result.index = [label(s) if s != portfolio_name else s for s in result.index]
        bars = result.reset_index(names='標的')
        mean_volatility = float(volatility.drop(portfolio_name).mul(weights).sum())
        st.caption(f"金色虛線：依起始比重加權的個別年化波動 {mean_volatility:.1f}%（不含組合）；青綠色：{portfolio_name}。")
        bar_chart = alt.Chart(bars).mark_bar(cornerRadiusEnd=4).encode(y=alt.Y('標的:N',sort='-x',title=None),x=alt.X('年化波動 (%):Q', title='年化波動 (%)'),color=alt.condition(alt.datum.標的==portfolio_name,alt.value('#35E0CE'),alt.value('#536B91')),tooltip=['標的:N',alt.Tooltip('年化波動 (%):Q',format='.1f')])
        reference = alt.Chart(pd.DataFrame({'年化波動 (%)':[mean_volatility], '說明':['依起始比重加權的個別波動（不含組合）']})).mark_rule(color='#F3C969', strokeWidth=2, strokeDash=[6,4]).encode(x=alt.X('年化波動 (%):Q', title='年化波動 (%)'), tooltip=['說明:N',alt.Tooltip('年化波動 (%):Q',format='.1f')])
        st.altair_chart((bar_chart + reference).properties(height=max(220,len(bars)*30)), width='stretch')
        st.dataframe(result.style.format('{:.1f}%'), width='stretch')
        st.caption("此比較呈現特定期間的歷史結果，不代表最佳配置。最大回撤可能未改善；相關性也可能在市場壓力下升高。")

    with st.container(border=True):
        from module_compat import load_renderer
        render_insights = load_renderer("insights", "render_insights", "weights")
        render_insights(volatility, drawdown, corr, daily, segment, label, basis, weights, portfolio_name)
