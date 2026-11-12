"""報酬順序風險：the same years of return, run in a different order.

Two experiments from 《投資 10 年就退休》 ch.3. Rearranging one set of real annual returns
(original, reversed, losses first, losses last, and every other order) is a stress test: it
shows how much the order alone moves the outcome, and it is not something that happened.
Starting the same retirement in different real years is history. The page labels each.

Only real ETF prices, and only configurations with MIN_YEARS whole calendar years: the
user's call (2026-11-12), so nothing here leans on a stand-in index. Configurations are
ranked over the years they all share, so none is credited for a stretch of market another
did not have to live through.
"""
from datetime import date, datetime
from itertools import permutations
from math import factorial
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from allocation import PRESETS
from retirement_strategy import BUFFER_SYMBOLS, TRANSFER_RATE, WITHDRAW_RATE

MIN_YEARS = 5
HISTORY_FROM = date(2000, 1, 1)
DEFAULT_PRINCIPAL_WAN = 3000.0
DEFAULT_RATE = 4.0
# Ten years for every start, so starts are compared over the same length of retirement;
# the book's 老周 A and B ran 17 each.
START_HORIZON = 10
# Every order is run when there are few enough of them; 6 years is 720. Past this the
# orders are sampled -- 17 years has about 3.6e14.
EXACT_UP_TO = 8
SAMPLES = 20_000
SEED = 20261112
# A series that opens in the first days of January counts that year whole: 0050's Yahoo
# history begins 2009-01-02, and the year it opens in is the one the book's 老周 B retired
# into. A year counts only if its data reaches the last days of December.
OPENS_BY_DAY = 10
CLOSES_FROM_DAY = 20

CURRENT = '自訂'
ORIGINAL = '原始順序'
ORDERS = (ORIGINAL, '反轉順序', '負報酬在前', '負報酬在後')
REAL = '真實歷史'
ARTIFICIAL = '人為排列（非真實歷史）'
# The app's categorical colours (.streamlit/config.toml), in its order.
COLORS = ['#60A5FA', '#34D399', '#A78BFA', '#FBBF24', '#F87171', '#38BDF8', '#FB923C', '#F472B6']


def order_label(order):
    return f'{order}（{REAL}）' if order == ORIGINAL else f'{order}（人為排列）'


# ------------------------------------------------------------------ data
def complete_years(prices, today):
    """Calendar-year returns, whole years only, before the current one.

    A year's base is the previous year's last close, or the year's own first close when the
    series opens within its first days -- see OPENS_BY_DAY.
    """
    prices = prices.dropna().sort_index()
    if prices.empty:
        return pd.Series(dtype=float)
    closes = prices.groupby(prices.index.year).last()
    out = {}
    for year in closes.index:
        if year >= today.year:
            continue
        days = prices[prices.index.year == year]
        if days.index[-1] < pd.Timestamp(year, 12, CLOSES_FROM_DAY):
            continue
        if year - 1 in closes.index:
            base = closes[year - 1]
        elif days.index[0] <= pd.Timestamp(year, 1, OPENS_BY_DAY):
            base = days.iloc[0]
        else:
            continue
        out[int(year)] = float(closes[year] / base - 1)
    return pd.Series(out, dtype=float)


def configuration_returns(histories, weights, today):
    """One configuration's holdings, year by year, over the years every one of them has.

    Returns (returns frame, None) or (None, why it cannot be assessed). The reason names
    the holding that holds the others back, since that is the one a reader can act on.
    """
    missing = [s for s in weights.index if s not in histories]
    if missing:
        return None, '無法取得行情：' + '、'.join(s.split('.')[0] for s in missing)
    yearly = {s: complete_years(histories[s], today) for s in weights.index}
    frame = pd.DataFrame(yearly).dropna(how='any').sort_index()
    if len(frame) >= MIN_YEARS:
        return frame, None
    shortest = min(yearly, key=lambda s: len(yearly[s]))
    first = histories[shortest].dropna().index[0]
    return None, (f'{shortest.split(".")[0]} 自 {first:%Y-%m} 才有資料，'
                  f'只有 {len(frame)} 個完整年度（門檻 {MIN_YEARS} 年）')


def buffer_split(weights):
    """The growth holdings' weights and the buffer's symbol, or None for no buffer pool."""
    buffer = [s for s in weights.index if s in BUFFER_SYMBOLS and weights[s] > 0]
    growth = weights.drop(index=buffer)
    growth = growth[growth > 0]
    if len(buffer) != 1 or growth.empty:
        return None
    return growth, buffer[0]


# ------------------------------------------------------------------ orders
def book_orders(blended):
    """The book's four orders of one set of years, as index arrays.

    Losses and gains keep their original order within each group, as the book does.
    """
    index = np.arange(len(blended))
    losses = [i for i in index if blended[i] < 0]
    gains = [i for i in index if blended[i] >= 0]
    return {ORIGINAL: index, '反轉順序': index[::-1],
            '負報酬在前': np.array(losses + gains, dtype=int),
            '負報酬在後': np.array(gains + losses, dtype=int)}


def every_order(n, samples=SAMPLES, seed=SEED):
    """Every order of n years when that is few enough to run, a seeded sample otherwise.

    The original order is always row 0, so a sample can still say where history fell.
    """
    if n <= EXACT_UP_TO:
        return np.array(list(permutations(range(n))), dtype=int), True
    rng = np.random.default_rng(seed)
    drawn = np.argsort(rng.random((samples, n)), axis=1)
    return np.vstack([np.arange(n), drawn]), False


# ------------------------------------------------------------------ the two rules
def fixed_withdrawal(returns, weights, principal, amount, orders):
    """The book's rule: a fixed sum out at the start of every year, no inflation step.

    Sold from each holding in proportion and never rebalanced, as everywhere else in the
    app. A year that opens with less than the sum pays out what is left and ends the account.
    Returns totals (orders, years + 1) and the year each order ran dry in, 0 if it never did.
    """
    r = np.asarray(returns, dtype=float)[orders]          # orders × years × holdings
    paths, years = r.shape[:2]
    value = np.tile(principal * np.asarray(weights, dtype=float), (paths, 1))
    totals = np.empty((paths, years + 1))
    totals[:, 0] = value.sum(axis=1)
    dry = np.zeros(paths, dtype=int)
    for k in range(years):
        held = value.sum(axis=1)
        enough = held > amount
        keep = np.where(enough, 1 - amount / np.where(held > 0, held, 1), 0.0)
        value = value * keep[:, None]
        dry[(~enough) & (dry == 0)] = k + 1
        value = value * (1 + r[:, k, :])
        totals[:, k + 1] = value.sum(axis=1)
    return totals, dry


def monthly_steps(returns, orders):
    """Each year's return spread evenly over its twelve months, after a January of none.

    Month 0 is the first January, when the rule transfers before anything has moved, and
    year k then grows over months 12k+1 to 12k+12 -- so the transfer opens every year, as
    the book's withdrawal does.
    """
    r = np.asarray(returns, dtype=float)[orders]
    per_month = np.repeat((1 + r) ** (1 / 12) - 1, 12, axis=1)
    return np.concatenate([np.zeros_like(per_month[:, :1]), per_month], axis=1)


def buffer_rule(returns, growth_weights, buffer_column, principal, share, orders,
                transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """retirement_strategy.backtest()'s loop over many orders at once.

    `returns` is years × holdings with the buffer at `buffer_column`; `growth_weights`
    covers the other columns. The growth pool is bought at its opening weights and left
    to drift, as growth_pool() does. Returns the year's income (orders, years) and the
    totals at each year's end (orders, years + 1). test_sequence_risk checks it against
    backtest() itself.
    """
    steps = monthly_steps(returns, orders)                # orders × months × holdings
    paths, months = steps.shape[:2]
    columns = [c for c in range(steps.shape[2]) if c != buffer_column]
    w = np.asarray(growth_weights, dtype=float)
    w = w / w.sum()
    index = (w * np.cumprod(1 + steps[:, :, columns], axis=1)).sum(axis=2)
    growth_step = np.zeros((paths, months))
    growth_step[:, 1:] = index[:, 1:] / index[:, :-1] - 1
    buffer_step = steps[:, :, buffer_column]
    growth = np.full(paths, principal * share)
    buffer = np.full(paths, principal * (1 - share))
    draw = np.zeros(paths)
    incomes, totals = [], [growth + buffer]
    for t in range(months):
        if t % 12 == 0:
            if t:
                totals.append(growth + buffer)
            if t == months - 1:
                break
            transfer = growth * transfer_rate
            growth, buffer = growth - transfer, buffer + transfer
            annual = buffer * withdraw_rate
            draw = annual / 12
            incomes.append(annual)
        spent = np.minimum(draw, np.maximum(buffer, 0.0))
        buffer = buffer - spent
        growth = growth * (1 + growth_step[:, t])
        buffer = buffer * (1 + buffer_step[:, t])
    return np.stack(incomes, axis=1), np.stack(totals, axis=1)


# ------------------------------------------------------------------ assessment
def assess(returns, weights, principal, rate, orders):
    """Both rules over the given orders of one configuration's years."""
    amount = principal * rate
    totals, dry = fixed_withdrawal(returns.to_numpy(), weights.reindex(returns.columns).to_numpy(),
                                   principal, amount, orders)
    out = {'totals': totals, 'dry': dry, 'income': None}
    split = buffer_split(weights)
    if split is not None:
        growth, buffer = split
        columns = list(growth.index) + [buffer]
        frame = returns[columns]
        income, pool_totals = buffer_rule(frame.to_numpy(), growth.to_numpy(), len(columns) - 1,
                                          principal, float(growth.sum() / weights.sum()), orders)
        out.update(income=income, pool_totals=pool_totals)
    return out


def ranking(window_returns, configs, principal, rate):
    """One row per configuration over the shared years, most order-sensitive first.

    The measure is the best order's ending total over the worst's. With no withdrawal every
    order ends at the same total, so whatever spread there is comes from the order alone,
    not from one configuration having had better years than another.
    """
    rows, runs = [], {}
    for name, frame in window_returns.items():
        orders, exact = every_order(len(frame))
        run = assess(frame, configs[name], principal, rate, orders)
        runs[name] = (orders, run)
        ending = run['totals'][:, -1]
        worst, best = float(ending.min()), float(ending.max())
        row = {'配置': name,
               '順序差距倍數': best / worst if worst > 0 else float('inf'),
               '最差順序期末（萬）': worst / 1e4,
               'P10 期末（萬）': float(np.percentile(ending, 10)) / 1e4,
               '中位期末（萬）': float(np.median(ending)) / 1e4,
               'P90 期末（萬）': float(np.percentile(ending, 90)) / 1e4,
               '歸零的排列': int((run['dry'] > 0).sum()),
               '排列數': len(orders)}
        if run['income'] is not None:
            income = run['income']
            row['緩衝池規則：最差順序生活費最低／首年'] = float((income.min(axis=1) / income[:, 0]).min())
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table, runs
    table = table.sort_values(['歸零的排列', '順序差距倍數', '最差順序期末（萬）'],
                              ascending=[False, False, True], kind='stable').reset_index(drop=True)
    table.insert(0, '排名', range(1, len(table) + 1))
    return table, runs


def start_years(returns, weights, principal, rate, horizon=START_HORIZON):
    """Each real starting year run for `horizon` years, in the order they happened."""
    rows = []
    for first in range(len(returns) - horizon + 1):
        frame = returns.iloc[first:first + horizon]
        run = assess(frame, weights, principal, rate, np.arange(horizon)[None, :])
        row = {'退休年': int(frame.index[0]), '期間': f'{frame.index[0]}–{frame.index[-1]}',
               '期末（萬）': float(run['totals'][0, -1]) / 1e4,
               '歸零年': int(run['dry'][0]) or None}
        if run['income'] is not None:
            income = run['income'][0]
            row['生活費最低／首年'] = float(income.min() / income[0])
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ page
@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
def load_histories(today, symbols):
    """Every holding's whole history. `today` keys the cache, as backtest_prices does."""
    from market import load_frame
    histories, failures, _, _ = load_frame(list(symbols), HISTORY_FROM, today, 'Adj Close')
    return histories, failures


def configurations(current_weights=None):
    configs = {name: pd.Series({s: w / 100 for s, w in c['weights'].items()})
               for name, c in PRESETS.items()}
    if current_weights is not None and len(current_weights):
        configs[CURRENT] = pd.Series(current_weights, dtype=float)
    return configs


def _badge(kind):
    st.badge(kind, color='green' if kind == REAL else 'orange')


def _wan(value):
    return f'{value:,.0f} 萬'


def _times(value):
    # As how much more the best order ends with than the worst, to two places: over a run of
    # strong years the configurations sit within thousandths of each other as ratios, and
    # 1.102 against 1.102 printed a tie the ranking does not have.
    return '無法計算（最差順序歸零）' if value == float('inf') else f'{value - 1:+.2%}'


def render_sequence_risk(current_weights=None):
    st.subheader('報酬順序風險')
    st.caption('同樣的報酬，只要出現的順序不同，退休後的結果就可能差很多。'
               '這一頁用實際 ETF 價格，評估每個配置對順序有多敏感。')
    principal = st.session_state.get('seq_principal_wan', DEFAULT_PRINCIPAL_WAN) * 1e4
    rate = st.session_state.get('seq_rate', DEFAULT_RATE) / 100
    configs = configurations(current_weights)
    symbols = tuple(sorted({s for w in configs.values() for s in w.index}))
    today = datetime.now(ZoneInfo('Asia/Taipei')).date()
    with st.spinner('正在取得各持股的完整歷史…'):
        histories, failures = load_histories(today, symbols)
    usable, excluded = {}, {}
    for name, weights in configs.items():
        frame, why = configuration_returns(histories, weights, today)
        if frame is None:
            excluded[name] = why
        else:
            usable[name] = frame
    if not usable:
        st.warning('沒有任何配置有 5 個以上的完整年度，無法評估。')
        return
    shared = sorted(set.intersection(*(set(f.index) for f in usable.values())))
    window = {name: f.loc[shared] for name, f in usable.items()}
    table, runs = ranking(window, configs, principal, rate)

    # ---------------------------------------------------------- 1. ranking, first thing
    st.markdown('### 報酬順序風險排名')
    _badge(ARTIFICIAL)
    st.caption(f'此排名用同一組真實年報酬（{shared[0]}–{shared[-1]}，共 {len(shared)} 年，'
               f'所有納入配置的共同年度）的所有排列計算，衡量的是「順序不同時結果差多少」，'
               f'不是預測哪個配置未來表現較好。固定提領：每年年初領本金的 {rate:.1%}'
               f'（{_wan(principal * rate / 1e4)}），不調整通膨。')
    top = table.iloc[0]
    times = top['順序差距倍數']
    best = '—' if times == float('inf') else _wan(top['最差順序期末（萬）'] * times)
    st.markdown(f'**{top["配置"]} 的順序風險最高**：同一組 {len(shared)} 年的報酬，最好與最差的順序，'
                f'最好的順序期末資產比最差的多 **{_times(times)}**（最差 {_wan(top["最差順序期末（萬）"])}、最好 {best}）。'
                f'順序風險最低的是 **{table.iloc[-1]["配置"]}**（{_times(table.iloc[-1]["順序差距倍數"])}）。')
    shown = table.copy()
    shown['順序差距倍數'] = shown['順序差距倍數'].map(_times)
    shown = shown.rename(columns={'順序差距倍數': '順序差距（最好比最差多）'})
    st.dataframe(shown, hide_index=True, width='stretch', column_config={
        **{c: st.column_config.NumberColumn(c, format='%,.0f') for c in shown.columns if '（萬）' in c},
        '緩衝池規則：最差順序生活費最低／首年': st.column_config.NumberColumn(
            '緩衝池規則：最差順序生活費最低／首年', format='percent')})
    st.caption('順序差距＝所有排列中，最好順序的期末資產比最差順序多幾 %；不提領時一定是 0%，'
               '所以差距完全來自順序。有排列歸零的配置排在最前。緩衝池規則那一欄只有含緩衝池的配置才有，'
               '不參與排名；它表示最差順序下，生活費最低落到首年的幾成。')
    if excluded:
        st.caption('**未納入（完整年度不足）**：' + '；'.join(f'{n}：{why}' for n, why in excluded.items()))
        if '退休10' in excluded and '退休8' in usable:
            st.caption('退休10 與退休8 只差 009816 換成 0050，退休8 是它目前最接近的替身。')
    st.caption('只用實際 ETF 價格，所以沒有任何配置涵蓋 2008 年金融海嘯（最早的 0050 在 Yahoo 從 2009 年起）。')
    with st.expander('調整假設（本金、提領率）'):
        st.number_input('本金（萬元）', min_value=100.0, step=100.0, format='%.0f',
                        value=DEFAULT_PRINCIPAL_WAN, key='seq_principal_wan')
        st.slider('固定提領率（每年領本金的 %）', min_value=1.0, max_value=8.0, step=0.5,
                  value=DEFAULT_RATE, key='seq_rate',
                  help='只影響書上的固定提領。緩衝池規則用它自己的撥出率 4%、領出率 25%。')

    # ---------------------------------------------------------- 2. one configuration
    st.markdown('### 個別配置：書上的四種順序')
    _badge(ARTIFICIAL)
    names = list(table['配置'])
    chosen = st.selectbox('選擇配置', names, index=0, key='seq_config')
    frame = window[chosen]
    weights = configs[chosen]
    blended = (frame * weights.reindex(frame.columns)).sum(axis=1).to_numpy() / float(weights.sum())
    four = book_orders(blended)
    run = assess(frame, weights, principal, rate, np.stack(list(four.values())))
    years = [str(y) for y in frame.index]
    st.caption(f'{chosen} 在 {years[0]}–{years[-1]} 的真實年報酬：'
               + '、'.join(f'{y} {r:+.1%}' for y, r in zip(years, blended))
               + '。只有「原始順序」是實際發生的；其他三種是把同一組年報酬重新排列。')
    balance = pd.DataFrame([{'退休後第幾年': k, '順序': order_label(o), '帳戶餘額（萬）': run['totals'][i, k] / 1e4}
                            for i, o in enumerate(four) for k in range(len(frame) + 1)])
    order_scale = alt.Scale(domain=[order_label(o) for o in ORDERS], range=['#F1F5F9'] + COLORS[3:6])
    dash = alt.condition(alt.datum['順序'] == order_label(ORIGINAL), alt.value([1, 0]), alt.value([5, 3]))
    st.markdown('**固定提領**（書上的做法）：帳戶餘額')
    st.altair_chart(alt.Chart(balance).mark_line(point=True, strokeWidth=2).encode(
        x=alt.X('退休後第幾年:O', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('帳戶餘額（萬）:Q', axis=alt.Axis(format=',.0f')),
        color=alt.Color('順序:N', scale=order_scale, legend=alt.Legend(orient='bottom', columns=2, title=None)),
        strokeDash=dash,
        tooltip=['順序:N', '退休後第幾年:O', alt.Tooltip('帳戶餘額（萬）:Q', format=',.0f')]
    ).properties(height=320), width='stretch')
    if run['income'] is not None:
        income = pd.DataFrame([{'退休後第幾年': k + 1, '順序': order_label(o), '年生活費（萬）': run['income'][i, k] / 1e4}
                               for i, o in enumerate(four) for k in range(len(frame))])
        st.markdown('**緩衝池規則**（成長池每年撥 4%、緩衝池領 25%）：每年生活費')
        st.altair_chart(alt.Chart(income).mark_line(point=True, strokeWidth=2).encode(
            x=alt.X('退休後第幾年:O', axis=alt.Axis(labelAngle=0)),
            y=alt.Y('年生活費（萬）:Q', axis=alt.Axis(format=',.0f')),
            color=alt.Color('順序:N', scale=order_scale, legend=alt.Legend(orient='bottom', columns=2, title=None)),
            strokeDash=dash,
            tooltip=['順序:N', '退休後第幾年:O', alt.Tooltip('年生活費（萬）:Q', format=',.1f')]
        ).properties(height=280), width='stretch')
    else:
        st.caption(f'{chosen} 沒有緩衝池，只看固定提領。')
    orders, full = runs[chosen]
    ending = pd.DataFrame({'期末資產（萬）': full['totals'][:, -1] / 1e4})
    st.markdown(f'**全部 {len(orders)} 種排列的期末資產分布**（固定提領；白線是原始順序）')
    original = float(full['totals'][0, -1]) / 1e4
    st.altair_chart((alt.Chart(ending).mark_bar(color=COLORS[0]).encode(
        x=alt.X('期末資產（萬）:Q', bin=alt.Bin(maxbins=30), title='期末資產（萬）', axis=alt.Axis(format=',.0f')),
        y=alt.Y('count():Q', title='排列數'),
        tooltip=[alt.Tooltip('期末資產（萬）:Q', bin=True, format=',.0f'), alt.Tooltip('count():Q', title='排列數')])
        + alt.Chart(pd.DataFrame({'x': [original]})).mark_rule(color='#F1F5F9', strokeWidth=2).encode(x=alt.X('x:Q', title='期末資產（萬）'))
    ).properties(height=220), width='stretch')
    with st.expander('表格檢視'):
        st.dataframe(balance.pivot(index='退休後第幾年', columns='順序', values='帳戶餘額（萬）').round(0), width='stretch')

    # ---------------------------------------------------------- 3. real starting years
    long = {n: f for n, f in usable.items() if len(f) >= START_HORIZON + 2}
    st.markdown('### 不同退休起點')
    _badge(REAL)
    if not long:
        st.caption(f'沒有配置有 {START_HORIZON + 2} 年以上的完整年度，無法比較不同起點。')
    else:
        st.caption(f'書上老周 A／B 的做法：同樣的本金與提領，只差哪一年退休。每個起點都看 {START_HORIZON} 年，'
                   f'用的是實際發生的年份順序。只有 {"、".join(long)} 的資料夠長。')
        starts = pd.concat([start_years(f, configs[n], principal, rate).assign(配置=n) for n, f in long.items()])
        st.altair_chart(alt.Chart(starts).mark_bar().encode(
            x=alt.X('退休年:O', axis=alt.Axis(labelAngle=0)), xOffset='配置:N',
            y=alt.Y('期末（萬）:Q', title=f'{START_HORIZON} 年後帳戶餘額（萬）', axis=alt.Axis(format=',.0f')),
            color=alt.Color('配置:N', scale=alt.Scale(domain=list(long), range=COLORS[:len(long)]),
                            legend=alt.Legend(orient='bottom', title=None)),
            tooltip=['配置:N', '期間:N', alt.Tooltip('期末（萬）:Q', format=',.0f')]
        ).properties(height=280), width='stretch')
        for name, part in starts.groupby('配置', sort=False):
            best, worst = part.loc[part['期末（萬）'].idxmax()], part.loc[part['期末（萬）'].idxmin()]
            line = (f'**{name}**：最好是 {best["退休年"]} 年退休（{_wan(best["期末（萬）"])}），'
                    f'最差是 {worst["退休年"]} 年（{_wan(worst["期末（萬）"])}），相差 '
                    f'{best["期末（萬）"] / worst["期末（萬）"]:.2f} 倍。')
            if '生活費最低／首年' in part and part['生活費最低／首年'].notna().any():
                line += f' 緩衝池規則下，生活費最低落到首年的 {part["生活費最低／首年"].min():.0%}。'
            st.markdown(line)
        with st.expander('表格檢視'):
            st.dataframe(starts, hide_index=True, width='stretch')

        # ------------------------------------------------------ 4. the long window
        st.markdown(f'### 長期：{"、".join(long)} 的完整歷史')
        _badge(ARTIFICIAL)
        rows = []
        for name, f in long.items():
            orders, exact = every_order(len(f))
            r = assess(f, configs[name], principal, rate, orders)
            w = configs[name]
            book = book_orders((f * w.reindex(f.columns)).sum(axis=1).to_numpy() / float(w.sum()))
            b = assess(f, w, principal, rate, np.stack(list(book.values())))
            end = r['totals'][:, -1] / 1e4
            row = {'配置': name, '期間': f'{f.index[0]}–{f.index[-1]}（{len(f)} 年）',
                   '排列': f'{len(orders):,} 種' + ('' if exact else '（抽樣）'),
                   '最差（萬）': end.min(), 'P10（萬）': np.percentile(end, 10), '中位（萬）': np.median(end),
                   'P90（萬）': np.percentile(end, 90), '歸零比例': float((r['dry'] > 0).mean())}
            for i, o in enumerate(book):
                row[f'{o}（萬）'] = b['totals'][i, -1] / 1e4
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', column_config={
            **{c: st.column_config.NumberColumn(c, format='%,.0f') for c in rows[0] if '（萬）' in c},
            '歸零比例': st.column_config.NumberColumn('歸零比例', format='percent')})
        st.caption(f'「{ORIGINAL}（萬）」是真實歷史，其他都是人為排列。不和上方的排名比較：年數不同。'
                   'Yahoo 的 0050 還原價格漏記 2009–2012 年配息，2014 年 10 月那筆又多算一次，'
                   '所以含 0050 的長期數字有誤差；上方排名用 2020 年以後的年度，不受影響。')
