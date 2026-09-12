"""Side-by-side comparison of whole allocations rather than individual holdings.

Each configuration becomes one wealth path, and that path is then treated exactly like a
price series: cumulative return, drawdown and the risk table all come from compare_prices,
so a configuration is measured by the same definitions as a holding on the 行情比較 page.
"""
import pandas as pd
import streamlit as st

from allocation import PRESETS
from correlation import analysis_data, portfolio_stats
from lightweight_chart import COLORS, render_chart
from market import compare_prices, load_frame
from ui import period_banner

CURRENT = '目前配置'
# Cards per row on the composition strip; see render_strategies for why it is not one row.
PER_ROW = 3


def allocation_table(current_weights=None, current_name=None):
    """The shipped presets, plus whatever the sidebar is currently set to."""
    table = {name: pd.Series({s: w / 100 for s, w in config['weights'].items()})
             for name, config in PRESETS.items()}
    if current_weights is not None and len(current_weights):
        table[f'{CURRENT}（{current_name}）'] = current_weights
    return table


def configuration_paths(prices, allocations):
    """One wealth path per configuration, all on the single window where every holding of
    every chosen configuration traded.

    Comparing configurations over windows of their own would reward whichever one happened
    to hold the youngest fund, so the window is the intersection and nothing else.
    """
    used = sorted({s for weights in allocations.values() for s in weights.index})
    absent = [s for s in used if s not in prices.columns]
    if absent:
        raise ValueError('缺少行情：' + '、'.join(absent))
    segment = analysis_data(prices[used])[2]
    if len(segment) < 2:
        raise ValueError('這些配置沒有足夠的共同交易日，請減少比較的配置或延長區間。')
    return pd.DataFrame({name: portfolio_stats(segment[list(weights.index)], weights)[0]
                         for name, weights in allocations.items()})


def binding_holding(prices, allocations):
    """The one holding whose late start sets the shared window, and who holds it.

    Every configuration built on it is paying for it, which is the actionable part: drop
    those and the comparison can run over a longer history.
    """
    used = sorted({s for weights in allocations.values() for s in weights.index})
    starts = {s: prices[s].first_valid_index() for s in used
              if s in prices.columns and prices[s].first_valid_index() is not None}
    if len(set(starts.values())) < 2:
        return None
    symbol = max(starts, key=lambda s: starts[s])
    return symbol, starts[symbol], [n for n, w in allocations.items() if symbol in w.index]


def percent(value):
    """50% rather than 50.0%, but a third of a portfolio still needs its decimal."""
    text = f'{value:.1f}'
    return (text[:-2] if text.endswith('.0') else text) + '%'


def composition_rows(weights, label):
    """The holdings of one configuration, heaviest first.

    A holding set to 0% is still listed: it is on the comparison list deliberately, and
    leaving it out would make the configuration look like it was never considered.
    """
    ordered = weights.sort_values(ascending=False, kind='stable')
    return [(label(symbol), percent(weight * 100)) for symbol, weight in ordered.items()]


def render_strategies(label, basis, start, end, weights=None, portfolio_name='等權重組合'):
    st.subheader('配置比較')
    st.caption('STRATEGY LAB · 同一段期間、同一個起點，比較不同配置的走勢')
    table = allocation_table(weights, portfolio_name)
    chosen = st.multiselect('要比較的配置', list(table), default=list(table),
                            help='每個配置依其比重買進後持有、不再平衡。')
    if len(chosen) < 1:
        st.info('請至少選擇一個配置。')
        return
    allocations = {name: table[name] for name in chosen}
    symbols = sorted({s for w in allocations.values() for s in w.index})
    field = 'Adj Close' if basis.startswith('還原') else 'Close'
    with st.spinner('正在取得這些配置所需的行情…'):
        histories, failures, _ = load_frame(symbols, start, end, field)
    if failures:
        st.warning('下列標的無法載入，含有它的配置無法比較：'
                   + '、'.join(label(s) for s in failures))
        return
    prices = pd.concat(histories, axis=1)
    try:
        paths = configuration_paths(prices, allocations)
        aligned, returns, drawdown, stats = compare_prices(paths)
    except ValueError as exc:
        st.warning(str(exc))
        return
    first, last = aligned.index[0], aligned.index[-1]
    period_banner(f'共同期間｜{first:%Y/%m/%d} — {last:%Y/%m/%d}',
                  f'{len(aligned):,} 個共同交易日 · {len(chosen)} 個配置 · {basis}')
    binding = binding_holding(prices, allocations)
    if binding and binding[1] > prices.index[0]:
        symbol, began, holders = binding
        st.caption(f'共同期間的起點由 {label(symbol)} 決定，它自 {began:%Y/%m/%d} 才有資料。'
                   f'含有它的配置：{"、".join(holders)}。移除這些配置可讓比較涵蓋更長的歷史。')
    view = st.segmented_control('圖表指標', ['累積漲跌幅', '歷史回撤'], default='累積漲跌幅',
                                label_visibility='collapsed', key='strategy_view',
                                help='累積漲跌幅：相對於共同起始日的漲跌。歷史回撤：相對於區間內截至當天最高點的跌幅。')
    chart_data = drawdown if view == '歷史回撤' else returns
    render_chart(chart_data, {c: c for c in chart_data.columns},
                 {c: COLORS[i % len(COLORS)] for i, c in enumerate(chart_data.columns)}, view,
                 key='strategy_chart')
    st.subheader('配置的報酬與風險')
    st.dataframe(stats.round(1).rename_axis('配置').reset_index(), hide_index=True, width='stretch',
                 column_config={c: st.column_config.NumberColumn(c, format='%.1f%%') for c in stats.columns})
    st.subheader('各配置的內容')
    st.caption('依起始比重買進後持有、不再平衡。比重顯示到小數一位，'
               '等分的配置（如衝刺的三分之一）相加會是 99.9%，實際計算用未四捨五入的值。')
    from ui import allocation_card
    # Three across, wrapping. Six cards fit the width only by breaking the holding names one
    # character per line: at this page's real content width each card would be about 85px.
    for start in range(0, len(chosen), PER_ROW):
        batch = chosen[start:start + PER_ROW]
        # Pad the last row so two cards do not stretch to half the page each.
        for column, name in zip(st.columns(PER_ROW, border=True), batch):
            with column:
                allocation_card(name, composition_rows(allocations[name], label))
    st.download_button('下載配置比較 CSV', returns.rename_axis('日期').to_csv(float_format='%.1f').encode('utf-8-sig'),
                       file_name=f'taiwan_strategies_{first:%Y%m%d}_{last:%Y%m%d}.csv',
                       mime='text/csv', icon=':material/download:')
    with st.expander('這一頁怎麼算的'):
        st.markdown("""
        - 每個配置**依其比重買進後持有、不再平衡**，與全站一致；未計交易成本與稅金。
        - 所有配置共用**同一個起始日與同一段期間**：被選配置的所有持股都有行情的交集。
          少了這個條件，持有較年輕基金的配置會因為期間較短而看起來較平穩。
        - **回撤是各配置自身淨值的回撤**，不是其持股回撤的加權平均 ——
          持股在不同日子見高點，加權平均會算出一個實際未發生的跌幅。
        - 報酬、回撤、年化報酬與年化波動的定義與「行情比較」頁完全相同。
          **共同期間不足 365 天時，年化報酬整欄留空**，這是刻意的：把幾個月的報酬
          外推成年化會誇大差距，而配置之間的差距正是這一頁要看的東西。
        - 配置的比重固定為設定值；`目前配置` 取自側邊欄，會隨你的調整而變。
        """)
