"""Optional investment illustration; cash distributions never added to Adj Close."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

UI_VERSION = 11


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def load_distributions(symbol, start, end):
    h = yf.Ticker(symbol).history(start=start.isoformat(), end=(end+timedelta(days=1)).isoformat(), auto_adjust=False, actions=True, timeout=15, raise_errors=True)
    if h.empty or not {'Close','Dividends','Stock Splits'}.issubset(h.columns):
        raise ValueError('缺少價格或配息事件資料')
    h.index = pd.DatetimeIndex(h.index).tz_localize(None).normalize()
    return h.loc[~h.index.duplicated(keep='last')].sort_index()


def cash_result(histories, weights, amount, first, last):
    rows, events = [], []
    for symbol, weight in weights.items():
        h = histories[symbol]
        p0, p1 = float(h.loc[first,'Close']), float(h.loc[last,'Close'])
        if not np.isfinite([p0,p1]).all() or min(p0,p1)<=0:
            raise ValueError('起訖價格無效')
        # Yahoo Close and distributions use split-adjusted units: do not split twice.
        units = amount*weight/p0
        dividends = h.loc[(h.index>first)&(h.index<=last),'Dividends']
        if dividends.isna().any() or (dividends<0).any():
            raise ValueError('配息事件無效')
        income = units*dividends.sum()
        trailing = h.loc[(h.index>last-pd.DateOffset(years=1))&(h.index<=last),'Dividends']
        coverage = h.index.min() <= last-pd.DateOffset(years=1)+pd.Timedelta(days=7)
        rows.append({'代碼':symbol,'投入金額':amount*weight,'期末市值':units*p1,'價差損益':units*p1-amount*weight,'期間除息金額':income,'含息損益':units*p1+income-amount*weight,'期間成本配息率 (%)':float(dividends.sum()/p0*100),'期末近12月殖利率 (%)':float(trailing.sum()/p1*100) if coverage else np.nan})
        for date, div in dividends[dividends>0].items():
            preceding = h.loc[h.index < date, 'Close']
            previous_close = float(preceding.iloc[-1]) if len(preceding) else np.nan
            event_yield = float(div / previous_close * 100) if np.isfinite(previous_close) and previous_close > 0 else np.nan
            events.append({'除息日':date.strftime('%Y/%m/%d'),'代碼':symbol,'每單位配息（元）':float(div),'當次配息殖利率 (%)':event_yield,'估計除息金額':float(div*units)})
    return pd.DataFrame(rows),pd.DataFrame(events)



def monthly_distributions(events, symbols, first, last):
    months = pd.period_range(first, last, freq='M').astype(str)
    index = pd.MultiIndex.from_product([months, symbols], names=['月份','代碼'])
    if events.empty:
        values = pd.Series(0.,index=index)
    else:
        grouped = events.assign(月份=pd.to_datetime(events['除息日']).dt.to_period('M').astype(str)).groupby(['月份','代碼'])['估計除息金額'].sum()
        values = grouped.reindex(index, fill_value=0.)
    result = values.rename('金額').reset_index()
    result['順序'] = result['代碼'].map({s:i for i,s in enumerate(symbols)})
    return result

def monthly_weights(segment, weights):
    """Sample actual last trading date in each month, preserving buy-and-hold drift."""
    values = segment.div(segment.iloc[0]).mul(weights, axis=1)
    shares = values.div(values.sum(axis=1), axis=0)
    samples = shares.groupby(shares.index.to_period('M')).tail(1)
    rows = []
    for date, row in samples.iterrows():
        bottom = 0.
        for order, symbol in enumerate(weights.index):
            share = float(row[symbol])
            rows.append({'月份': date.strftime('%Y-%m'), '日期': date.strftime('%Y/%m/%d'),
                         '代碼': symbol, '占比': share, '底部': bottom, '頂部': bottom + share,
                         '中央': bottom + share / 2, '順序': order,
                         '端點': date in (samples.index[0], samples.index[-1])})
            bottom += share
    return pd.DataFrame(rows)


def render_weight_tracking(segment, weights, label, basis):
    data = monthly_weights(segment, weights)
    data['標的'] = data['代碼'].map(label)
    data['數字'] = data['占比'].map(lambda v: f'{v:.1%}')
    palette = ['#3B9EFF','#FF922B','#D0A2FF','#FFE14A','#FF5263','#35E0CE','#C0ED55','#FF80CB','#F5F7FA','#BCA383','#90A4C2','#00C853']
    with st.container(border=True):
        st.subheader('占比追蹤｜不再平衡後的配置變化')
        st.caption('每月最後一個有效交易日取樣；最後一月截至試算期末。首尾月份標示占比，合計為 100%。首月為月末占比，可能與起始配置不同。')
        st.caption(f'{segment.index[0]:%Y/%m/%d} — {segment.index[-1]:%Y/%m/%d} · {basis} · 還原價格模式為含配息調整的價值占比，非實際持股市值占比。')
        tooltip = ['日期:N','標的:N',alt.Tooltip('占比:Q',format='.1%')]
        base = alt.Chart(data).encode(x=alt.X('月份:N',sort=sorted(data['月份'].unique()),title=None,axis=alt.Axis(labelAngle=-45)))
        bars = base.mark_bar().encode(
            y=alt.Y('頂部:Q',title='組合占比',scale=alt.Scale(domain=[0,1]),axis=alt.Axis(format='.0%')),
            y2='底部:Q', color=alt.Color('標的:N',scale=alt.Scale(domain=[label(s) for s in weights.index],range=palette[:len(weights)]),legend=alt.Legend(orient='bottom',columns=1,labelLimit=350)),tooltip=tooltip)
        numbers = base.transform_filter('datum.端點 && datum.占比 > 0').mark_text(color='#101828',fontWeight='bold',fontSize=11).encode(y=alt.Y('中央:Q',title='組合占比'),text='數字:N',tooltip=tooltip)
        st.altair_chart((bars + numbers).properties(height=360),width='stretch')
        with st.expander('查看每月占比數字（含小額配置）'):
            grid = data.pivot(index='月份',columns='標的',values='占比')
            st.dataframe(grid.style.format('{:.1%}'),width='stretch')


@st.fragment
def render_investment(prices, weights, amount, label, basis):
    if amount is None or amount <= 0:
        return
    st.subheader('投資報酬試算')
    if set(prices.columns) != set(weights.index):
        st.warning('部分標的資料缺失，金額試算暫停；不自動重新分配資金。')
        return
    from correlation import analysis_data
    _,_,segment = analysis_data(prices)
    if len(segment)<2:
        st.info('完整行情不足，無法試算。')
        return
    first,last=segment.index[0],segment.index[-1]
    value=(segment/segment.iloc[0]).mul(weights,axis=1).sum(axis=1)*amount
    st.caption(f'試算期間 {first:%Y/%m/%d} — {last:%Y/%m/%d} · 最長完整行情區段')
    st.caption('起初按比重一次投入、持有不再平衡；允許小數單位，未計交易成本、稅金。此為歷史理論試算。')
    total_tab, dividend_tab = st.tabs(['總報酬', '配息'])
    with total_tab:
        with st.container(key='investment_summary'):
            cards = st.columns(4, wrap=False)
            cards[0].metric('區間報酬率', f'{(value.iloc[-1]/amount-1)*100:+.1f}%', border=True)
            for card,title,v in zip(cards[1:],['初始投入','期末試算價值','區間損益'],[amount,value.iloc[-1],value.iloc[-1]-amount]):
                card.metric(title,f'NT$ {v:,.0f}', border=True)
        st.html('<style>.st-key-investment_summary [data-testid="stColumn"]{min-width:250px!important}.st-key-investment_summary [data-testid="stMetricValue"]{font-size:clamp(20px,2vw,30px)}</style>')
        st.line_chart(value.rename('資產價值（元）'),color='#35CDBF')
        st.caption(f'最大高點至低點金額差：NT$ {(value.cummax()-value).max():,.0f}。還原價格試算不再另加配息。')
        allocations=pd.DataFrame({'標的':[label(s) for s in weights.index],'比重 (%)':weights.values*100,'投入金額':weights.values*amount})
        st.dataframe(allocations,hide_index=True,column_config={'比重 (%)':st.column_config.NumberColumn(format='%.1f'),'投入金額':st.column_config.NumberColumn(format='%.0f')})
        render_weight_tracking(segment, weights, label, basis)
        if not basis.startswith('還原'):
            st.caption('目前採收盤價，此報酬率不含現金配息；含息結果請查看配息子分頁。')
    with dividend_tab:
        st.caption('獨立採 Close＋除息事件計算，不將配息加到上方還原價格價值。除息金額不代表已付款入帳。')
        if not st.toggle('載入配息試算',key='cash_enabled'):
            return
        lookup_start=min(first,last-pd.DateOffset(years=1))-pd.Timedelta(days=7)
        def fetch(s):
            return s,load_distributions(s,lookup_start.date(),last.date())
        try:
            with st.spinner('正在取得配息資料（快取 1 小時）…'):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    histories=dict(pool.map(fetch,weights.index))
            table,events=cash_result(histories,weights,amount,first,last)
        except Exception:
            st.warning('部分配息資料無法取得，暫不計算合計，避免把缺資料當成零配息。可稍後重新開啟配息試算。')
            return
        income=table['期間除息金額'].sum()
        for card,title,v in zip(st.columns(3),['期間除息金額','期末市值＋除息金額','含息損益'],[income,table['期末市值'].sum()+income,table['含息損益'].sum()]):
            card.metric(title,f'NT$ {v:,.0f}')
        st.write(f'組合期間成本配息率：{income/amount*100:.1f}%（未年化）')
        st.caption('期末近12月殖利率＝截至試算期末前12個月每股配息÷期末價格，不是今日殖利率。歷史覆蓋不足一年時留空。未記錄配息不保證來源完整。')
        st.caption('使用 Yahoo 分割調整後的價格／配息單位，不重複乘分割倍數；不代表實際買入股數。起始日收盤買入，排除當日除息；配息不再投入。')
        table['代碼']=table['代碼'].map(label)
        st.markdown('#### 每月配息來源')
        st.caption('按除息月份估算，非實際入帳現金流。用於觀察歷史分布；生活費安排仍需確認付款日期，未來配息不保證。')
        monthly = monthly_distributions(events, list(weights.index), first, last)
        totals = monthly.groupby('月份', sort=True)['金額'].sum()
        for card, title, v in zip(st.columns(3), ['涵蓋月份平均','最低月份','零配息月份'], [f'NT$ {totals.mean():,.0f}', f'NT$ {totals.min():,.0f}', f'{int((totals==0).sum())} 個月']):
            card.metric(title,v)
        st.caption('平均包含零配息及首尾不完整月份，不代表每月固定可領金額。')
        monthly['標的'] = monthly['代碼'].map(label)
        monthly['月合計'] = monthly['月份'].map(totals)
        palette = ['#3B9EFF','#FF922B','#D0A2FF','#FFE14A','#FF5263','#35E0CE','#C0ED55','#FF80CB','#F5F7FA','#BCA383','#90A4C2','#00C853']
        chart = alt.Chart(monthly).mark_bar().encode(
            x=alt.X('月份:N', sort=sorted(totals.index), title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('金額:Q', stack='zero', title='每月除息金額（元）', axis=alt.Axis(format=',.0f')),
            color=alt.Color('標的:N', scale=alt.Scale(domain=[label(s) for s in weights.index],range=palette[:len(weights)]), legend=alt.Legend(orient='bottom',columns=1,labelLimit=350)),
            order=alt.Order('順序:Q'),
            tooltip=['月份:N','標的:N',alt.Tooltip('金額:Q',format=',.0f'),alt.Tooltip('月合計:Q',format=',.0f')])
        labels_data = totals.rename('月合計').reset_index()
        labels_data['顯示'] = labels_data['月合計'].map(lambda v: f'{v/10000:.1f}萬')
        labels_chart = alt.Chart(labels_data).mark_text(dy=-9, color='#F1F5F9', fontSize=12).encode(
            x=alt.X('月份:N', sort=sorted(totals.index), title=None),
            y=alt.Y('月合計:Q', title='每月除息金額（元）', scale=alt.Scale(domain=[0, max(float(totals.max())*1.18, 1)])),
            text='顯示:N', tooltip=['月份:N',alt.Tooltip('月合計:Q',format=',.0f')])
        st.altair_chart((chart + labels_chart).properties(height=320), width='stretch')
        with st.expander('每月各檔金額與合計'):
            grid=monthly.pivot(index='月份',columns='標的',values='金額')
            grid['合計']=totals
            st.dataframe(grid.style.format('{:,.0f}'),width='stretch')
        if income == 0:
            st.info('此試算期間沒有記錄到可計入的配息金額。')
        st.dataframe(table,hide_index=True,column_config={c:st.column_config.NumberColumn(format='%.1f' if '(%)' in c else '%.0f') for c in table if c!='代碼'})
        if not events.empty:
            events['代碼']=events['代碼'].map(label)
            st.dataframe(events,hide_index=True,column_config={'當次配息殖利率 (%)':st.column_config.NumberColumn(format='%.1f%%', help='當次每單位配息 ÷ 除息前一筆交易日收盤價 × 100%，未年化；前日價格無效時留空。'),'每單位配息（元）':st.column_config.NumberColumn(format='%.4f', help='Yahoo 分割調整單位的每單位配息，保留四位小數避免小額配息被四捨五入成零。'),'估計除息金額':st.column_config.NumberColumn(format='%.0f')})
