"""What the 退休5／退休6 presets actually do, and why each number in the rule is that number.

The rule is a dynamic withdrawal: every year a fixed share of the growth pool is moved into
a buffer, and a fixed share of the buffer is spent. The figures quoted against the design
come from the simulations recorded in WORKLOG 第四十、四十一次; the chart on the page is run
here, over the prices 退休6 actually has.
"""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from allocation import PRESETS
from ui import wan

# The withdrawal rate stays a constant: a quarter is what spreads one year's market over
# four, and the whole page is an explanation of that. The transfer rate is adjustable
# because it is the one that sets the level of the income rather than its smoothness, and
# seeing what a different one does to the same history is the point of asking.
TRANSFER_RATE = 0.04   # moved out of the growth pool each year
WITHDRAW_RATE = 0.25   # taken out of the buffer each year, i.e. a quarter
TRANSFER_RANGE = (1.0, 8.0)

# 00865B's measured return over its 6.8 years, from WORKLOG 第四十次. Only used to price
# the difference between taking the year's money out at once and taking it monthly.
BUFFER_YIELD = 0.0289
# Draw a twelfth at the start of each month and the money still in the pool earns, on
# average, 11/24 of a year that a lump sum at the start of the year would have missed.
HELD_FRACTION = 11 / 24

# The poster is the study's own artwork and stays with the study it came from.
POSTER = Path(__file__).resolve().parent.parent / 'analysis' / 'retirement5-original-100-12.png'

ORIGINAL = '原始設計 100：12'
PRESET = 'APP 預設（退休5／退休6）'

# 退休5 holds 009826, listed in July 2026, so it has no history to run the rule over.
# 退休6 is the same shape in instruments that do -- that is why it exists.
BACKTEST_PRESET = '退休6'
BACKTEST_FROM = date(2008, 1, 1)


def growth_share(shape):
    """The growth pool's share of the whole, read off the preset rather than restated here."""
    if shape == ORIGINAL:
        return 100 / 112
    weights = PRESETS['退休5']['weights']
    return max(weights.values()) / sum(weights.values())


def pool_plan(principal, share, transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """One year of the rule, from a principal to the money that reaches the wallet.

    Returned as a dict rather than a tuple: every one of these figures appears on the page
    with its own explanation, and positional unpacking would make that easy to get wrong.
    """
    growth = principal * share
    buffer = principal - growth
    transfer = growth * transfer_rate
    pooled = buffer + transfer
    spend = pooled * withdraw_rate
    return {'growth': growth, 'buffer': buffer, 'transfer': transfer, 'pooled': pooled,
            'spend': spend, 'monthly': spend / 12,
            'growth_left': growth - transfer, 'buffer_left': pooled - spend,
            'buffer_years': buffer / spend if spend else float('nan'),
            'spend_rate': spend / principal if principal else float('nan')}


def monthly_execution_gain(spend, annual_yield=BUFFER_YIELD):
    """What spreading one year's withdrawal over twelve months is worth.

    The rule fixes the amount once a year; this prices only the timing of taking it out,
    which is why it is a function of its own rather than another key in pool_plan.
    """
    return spend * annual_yield * HELD_FRACTION


def month_ends(growth_prices, buffer_prices):
    """The two series on the days both of them traded, one row per calendar month.

    Grouped by period rather than resampled: a resample invents a row for a month with no
    observation, and a NaN there would read as a month the pools were worth nothing.
    """
    paired = pd.concat({'growth': growth_prices, 'buffer': buffer_prices},
                       axis=1).dropna(how='any').sort_index()
    if paired.empty:
        return paired
    monthly = paired.groupby(paired.index.to_period('M')).last()
    monthly.index = monthly.index.to_timestamp(how='end').normalize()
    return monthly


def backtest(growth_prices, buffer_prices, principal, share,
             transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """Run the rule month by month over real prices, and record what it paid out.

    The year's amount is fixed once, on the anniversary, and then drawn a twelfth at a
    time -- which is what the 執行面 section says to do, and leaves the rest of it earning
    in the buffer rather than sitting in a wallet. Both pools are marked to the month's
    close after the draw, so each row is an end-of-month position.
    """
    monthly = month_ends(growth_prices, buffer_prices)
    if len(monthly) < 13:
        raise ValueError(f'需要至少 13 個月的共同行情，目前只有 {len(monthly)} 個月。')
    growth_step = monthly['growth'].pct_change().fillna(0.0)
    buffer_step = monthly['buffer'].pct_change().fillna(0.0)

    growth, buffer = principal * share, principal * (1 - share)
    annual = draw = 0.0
    rows = []
    for position, when in enumerate(monthly.index):
        if position % 12 == 0:
            transfer = growth * transfer_rate
            growth, buffer = growth - transfer, buffer + transfer
            annual = buffer * withdraw_rate
            draw = annual / 12
        # Never hand out money the buffer does not have; at a low enough transfer rate the
        # buffer shrinks, and an overdraft would quietly turn into a loan nobody agreed to.
        spent = min(draw, max(buffer, 0.0))
        buffer -= spent
        growth *= 1 + growth_step.iloc[position]
        buffer *= 1 + buffer_step.iloc[position]
        rows.append({'月份': when, '成長池': growth, '緩衝池': buffer,
                     '總資產': growth + buffer, '當月生活費': spent, '年生活費': annual})
    return pd.DataFrame(rows).set_index('月份')


def yearly_income(run):
    """What each anniversary year actually paid.

    Only whole years: the history ends mid-year, and a group of eleven months would read
    as the year the income collapsed.
    """
    whole = len(run) // 12 * 12
    if not whole:
        return pd.Series(dtype=float)
    paid = run['當月生活費'].iloc[:whole]
    return paid.groupby(pd.RangeIndex(whole) // 12).sum()


# Two readings on one picture, so they need to stay apart: the money you live on, and what
# it is coming out of. Gold is the income because that is the line a reader is here for.
INCOME_COLOUR = '#F5C451'
ASSET_COLOUR = '#35CDBF'


def backtest_holdings():
    weights = PRESETS[BACKTEST_PRESET]['weights']
    return max(weights, key=weights.get), min(weights, key=weights.get)


@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
def backtest_prices(today):
    """The two holdings of 退休6, over everything they have. `today` keys the cache."""
    from market import load_frame
    growth, buffer = backtest_holdings()
    histories, failures, _, _ = load_frame([growth, buffer], BACKTEST_FROM, today, 'Adj Close')
    if failures:
        raise ValueError('、'.join(f'{s}：{why[:100]}' for s, why in failures.items()))
    return histories[growth], histories[buffer]


# Measured off the series, never looked up: the window moves as the data does, and a list
# of dates written down here would go stale without anyone noticing.
EPISODE_THRESHOLD = 0.08
SHADE_DEEPER_THAN = 0.15
SHADE_COLOUR = '#FF5263'

# These names are the one thing on the chart that does not come out of the prices. They are
# general market knowledge, and the page says so -- an episode nobody here can name keeps
# its dates and its depth and goes unlabelled rather than being given a plausible story.
EPISODE_NAMES = {
    (2020, 3): 'COVID-19 疫情崩盤',
    (2022, 6): '2022 通膨升息空頭',
    (2024, 8): '2024 夏季全球急跌',
    (2025, 4): '2025 關稅衝擊',
}


def drawdown_episodes(prices, threshold=EPISODE_THRESHOLD):
    """Every peak-to-trough fall deeper than `threshold`, oldest first.

    An episode runs from the high it fell from to the day it got back there, so the
    recovery is part of it; the one still open at the end of the data has no recovery date
    and says so rather than pretending the last row is one.
    """
    prices = prices.dropna()
    if len(prices) < 2:
        return []
    drawdown = prices / prices.cummax() - 1
    spans, peak, falling = [], None, False
    for when, value in drawdown.items():
        if not falling and value < -1e-9:
            # The last day at the high, not the first: a high held for a week is not
            # a week of falling, and shading it as one would overstate every episode.
            history = prices.loc[:when]
            falling, peak = True, history[history == history.max()].index[-1]
        elif falling and value >= -1e-9:
            spans.append((peak, when))
            falling = False
    if falling:
        spans.append((peak, None))
    found = []
    for peak, recovered in spans:
        segment = drawdown.loc[peak:] if recovered is None else drawdown.loc[peak:recovered]
        if segment.min() > -threshold:
            continue
        trough = segment.idxmin()
        found.append({'高點': peak, '谷底': trough, '收復': recovered,
                      '跌幅': float(segment.min()),
                      '名稱': EPISODE_NAMES.get((trough.year, trough.month))})
    return found


def income_chart(run, episodes=()):
    """Monthly income as bars against total assets as a line, on their own scales.

    One scale for both would flatten the income to nothing: the bars are a month's living
    costs and the line is the principal they come out of, two orders of magnitude apart.
    The shaded spans are the growth pool's own falls, so what the income did through one is
    read off the same picture rather than taken on trust.
    """
    frame = run.reset_index()
    frame['每月生活費（萬）'] = frame['當月生活費'] / 10000
    frame['總資產（萬）'] = frame['總資產'] / 10000
    frame['成長池（萬）'] = frame['成長池'] / 10000
    frame['緩衝池（萬）'] = frame['緩衝池'] / 10000
    when = alt.X('月份:T', title=None, axis=alt.Axis(format='%Y', tickCount='year'))
    tooltip = [alt.Tooltip('月份:T', format='%Y/%m'),
               alt.Tooltip('每月生活費（萬）:Q', format='.2f'),
               alt.Tooltip('總資產（萬）:Q', format=',.0f'),
               alt.Tooltip('成長池（萬）:Q', format=',.0f'),
               alt.Tooltip('緩衝池（萬）:Q', format=',.0f')]
    layers = []
    marked = [e for e in episodes if e['跌幅'] <= -SHADE_DEEPER_THAN]
    if marked:
        spans = pd.DataFrame([
            {'起': e['高點'], '迄': e['收復'] or run.index[-1],
             '事件': e['名稱'] or '未命名的回撤', '跌幅': e['跌幅']} for e in marked])
        layers.append(alt.Chart(spans).mark_rect(opacity=.16, color=SHADE_COLOUR).encode(
            x=alt.X('起:T', title=None), x2='迄:T',
            tooltip=['事件:N', alt.Tooltip('起:T', format='%Y/%m'),
                     alt.Tooltip('迄:T', format='%Y/%m'),
                     alt.Tooltip('跌幅:Q', format='.1%')]))
    layers.append(alt.Chart(frame).mark_bar(color=INCOME_COLOUR, opacity=.9).encode(
        x=when, y=alt.Y('每月生活費（萬）:Q', title='每月生活費（萬元）',
                        axis=alt.Axis(titleColor=INCOME_COLOUR, labelColor=INCOME_COLOUR)),
        tooltip=tooltip))
    layers.append(alt.Chart(frame).mark_line(color=ASSET_COLOUR, strokeWidth=2.5).encode(
        x=when, y=alt.Y('總資產（萬）:Q', title='總資產（萬元）',
                        axis=alt.Axis(titleColor=ASSET_COLOUR, labelColor=ASSET_COLOUR,
                                      format=',.0f')),
        tooltip=tooltip))
    if marked:
        names = pd.DataFrame([
            {'起': e['高點'], '事件': (e['名稱'] or '回撤') + f" {e['跌幅']:.0%}"}
            for e in marked])
        layers.append(alt.Chart(names).mark_text(
            align='left', baseline='top', dx=4, dy=2, fontSize=11, color=SHADE_COLOUR
        ).encode(x=alt.X('起:T', title=None), y=alt.value(0), text='事件:N'))
    return alt.layer(*layers).resolve_scale(y='independent').properties(height=400)

def worst_fall_without_the_currency(prices, rates):
    """A NT$-quoted fund's worst fall, and what the same span did with the rate divided out.

    00865B holds US treasuries and quotes in NT$, so a strengthening NT$ reads on the chart
    as the buffer losing money while the asset behind it did nothing of the kind. The buffer
    is the part of this design that is supposed to hold still, so the difference between
    those two numbers is worth naming rather than leaving on the chart unexplained.
    """
    prices = prices.dropna()
    if len(prices) < 2 or rates is None or len(rates) == 0:
        return None
    drawdown = prices / prices.cummax() - 1
    trough = drawdown.idxmin()
    peak = prices.loc[:trough].idxmax()
    aligned = rates.reindex(prices.index.union(rates.index)).ffill().reindex(prices.index)
    in_dollars = (prices / aligned).dropna()
    if peak not in in_dollars.index or trough not in in_dollars.index:
        return None
    return {'跌幅': float(drawdown.min()), '高點': peak, '谷底': trough,
            '美元計價': float(in_dollars.loc[trough] / in_dollars.loc[peak] - 1)}


def _caption(card, title, value, note):
    card.metric(title, value, delta=note, delta_color='off', delta_arrow='off')


def _render_backtest(principal, share, transfer_rate):
    growth_symbol, buffer_symbol = backtest_holdings()
    st.markdown(f'### 這條規則走過真實行情：{BACKTEST_PRESET}')
    try:
        growth_prices, buffer_prices = backtest_prices(
            datetime.now(ZoneInfo('Asia/Taipei')).date())
        run = backtest(growth_prices, buffer_prices, principal, share, transfer_rate)
    except Exception as exc:
        st.warning(f'回測暫時無法進行：{exc}')
        st.caption('上面的年度試算不受影響，它不需要行情。')
        return

    first, last = run.index[0], run.index[-1]
    years = (last - first).days / 365.25
    st.caption(f'{growth_symbol} 成長池 ＋ {buffer_symbol} 緩衝池 · '
               f'{first:%Y/%m} — {last:%Y/%m}（{years:.1f} 年，{len(run)} 個月）· '
               f'起始 {wan(principal)} · 撥出率 {transfer_rate:.1%}、領出率 {WITHDRAW_RATE:.0%}')
    # Daily, and only over the window both holdings have. Month ends would have called
    # COVID a 22.3% fall when it was 33.6% and lost the 2025 one entirely; the growth
    # pool's own history reaches back to 2008, which is a decade the buffer -- and so
    # this chart -- knows nothing about. The shading is a span of dates either way.
    common = pd.concat({'growth': growth_prices, 'buffer': buffer_prices},
                       axis=1).dropna(how='any').sort_index()
    episodes = drawdown_episodes(common['growth'])
    st.altair_chart(income_chart(run, episodes), width='stretch')
    st.caption('金色長條：那個月實際領到的生活費（右軸為總資產，兩者刻度不同）。'
               '青綠色線：成長池＋緩衝池的合計市值，已扣掉每個月領走的錢。'
               '年度金額在每個週年重算一次，之後十二個月固定，所以長條是一年一階。'
               f'紅色區塊：成長池跌超過 {SHADE_DEEPER_THAN:.0%} 的期間，由高點畫到收復當月。')

    if episodes:
        rows = ['| 期間 | 成長池跌幅 | 收復 | 同期緩衝池 | 可能對應的事件 |', '|---|---|---|---|---|']
        for item in episodes:
            recovered = (f'{(item["收復"] - item["谷底"]).days} 天'
                         if item['收復'] is not None else '**尚未收復**')
            pool = common['buffer'].asof(item['谷底']) / common['buffer'].asof(item['高點']) - 1
            rows.append(f'| {item["高點"]:%Y/%m} — {item["谷底"]:%Y/%m} | '
                        f'{item["跌幅"]:.1%} | {recovered} | {pool:+.1%} | '
                        f'{item["名稱"] or "—"} |')
        with st.expander(f'這段歷史經歷過的震盪（成長池跌超過 {EPISODE_THRESHOLD:.0%} 的 '
                         f'{len(episodes)} 次）', expanded=True):
            st.markdown(chr(10).join(rows))
            st.caption('**日期與跌幅是從行情算出來的；最後一欄的名稱不是。** '
                       '那是一般市場認知，程式無法驗證，也不保證是唯一或主要的原因；'
                       '認不出來的就留白，不硬給一個說法。'
                       '「同期緩衝池」是同一段期間緩衝池自己的漲跌 —— '
                       '**這一欄才是這個設計成立與否的關鍵**：它撐住了，生活費才撐得住。')

    paid = yearly_income(run)
    cards = st.columns(4)
    _caption(cards[0], '期末總資產', wan(run['總資產'].iloc[-1]),
             f'起始 {wan(principal)}')
    _caption(cards[1], '首年生活費', wan(paid.iloc[0]) if len(paid) else '—',
             f'每月約 {wan(paid.iloc[0] / 12)}' if len(paid) else '')
    if len(paid) > 1:
        change = paid.iloc[-1] / paid.iloc[0] - 1
        _caption(cards[2], f'第 {len(paid)} 年生活費', wan(paid.iloc[-1]),
                 f'較首年 {change:+.1%}（名目，未計通膨）')
        worst = (paid.pct_change().dropna().min())
        _caption(cards[3], '最差的單年變化', f'{worst:+.1%}',
                 '同期成長池最大月底回撤 '
                 f'{(run["成長池"] / run["成長池"].cummax() - 1).min():.1%}')
    # A slider nobody can compare against is just a number that moves. Same history, same
    # principal, only the rate different -- that is the whole question being asked.
    if abs(transfer_rate - TRANSFER_RATE) > 1e-9:
        try:
            baseline = backtest(growth_prices, buffer_prices, principal, share, TRANSFER_RATE)
        except ValueError:
            baseline = None
        if baseline is not None:
            base_paid = yearly_income(baseline)
            st.markdown(
                f'#### 撥出率 {transfer_rate:.1%} 對上預設的 {TRANSFER_RATE:.1%}\n\n'
                '| 同一段歷史、同一筆本金 | '
                f'{TRANSFER_RATE:.1%}（預設） | {transfer_rate:.1%}（你設的） |\n|---|---|---|\n'
                f'| 首年生活費 | {wan(base_paid.iloc[0])} | **{wan(paid.iloc[0])}** |\n'
                f'| 第 {len(paid)} 年生活費 | {wan(base_paid.iloc[-1])} | **{wan(paid.iloc[-1])}** |\n'
                f'| 期末總資產 | {wan(baseline["總資產"].iloc[-1])} | '
                f'**{wan(run["總資產"].iloc[-1])}** |\n'
                f'| 期末緩衝池佔比 | {baseline["緩衝池"].iloc[-1] / baseline["總資產"].iloc[-1]:.1%} | '
                f'**{run["緩衝池"].iloc[-1] / run["總資產"].iloc[-1]:.1%}** |\n')
            st.caption('生活費領得多，期末資產就少 —— 兩欄一起看才看得出代價。'
                       '緩衝池佔比偏離一成，代表這個撥出率下規則的自我平衡點不在原來的位置。')

    # The buffer is the half of the design that is supposed to hold still. On this history
    # it did not, and the reason is not in the bonds -- so say which it was.
    from market import fx_rates
    currency = worst_fall_without_the_currency(buffer_prices, fx_rates())
    if currency and currency['跌幅'] <= -0.05:
        st.warning(
            f'**緩衝池自己也跌過 {abs(currency["跌幅"]):.1%}**'
            f'（{currency["高點"]:%Y/%m} → {currency["谷底"]:%Y/%m}），'
            f'但同一段期間用美元計價只有 {currency["美元計價"]:+.1%} —— '
            f'**那不是債券跌，是台幣升值。** {buffer_symbol} 持有的是美國公債、以台幣掛牌，'
            '沒有避險。對一個用台幣過日子的人來說，這代表'
            '**緩衝池並不像規則假設的那麼穩**，而成長池（VT）同樣是未避險的美元曝險，'
            '兩個池子會在台幣升值時一起縮水。'
            '**這是退休5／退休6 本身的性質，不是回測的瑕疵。**')

    st.caption('**這是一段 6.8 年的歷史，不是長期驗證。** 期間只夠涵蓋 2020 年的急跌與 '
               '2022 年的股債同跌，沒有一次完整的長空頭。'
               f'期間受 {buffer_symbol} 的上市日限制（{growth_symbol} 本身有更長的歷史）。'
               '未計稅、費用與交易成本；退休5 的 009826 於 2026 年才上市，'
               '所以這裡跑的是它的長歷史替身。')


def render_strategy():
    st.subheader('緩衝池退休法：成長池 ＋ 緩衝池')
    st.markdown(
        '**不是每年固定領多少錢，而是每年領走資產的一個比例。** 因為永遠只拿走一部分，'
        '這種規則在定義上不會把錢領到見底 —— 代價是收入會跟著市場上下。'
        '緩衝池的唯一工作，就是把那個上下壓平到能過日子的幅度。\n\n'
        '**年生活費 ＝（成長池 × 撥出率 ＋ 緩衝池）× 25%**')

    st.markdown('### 換成你的金額')
    left, middle, right = st.columns([1.1, 1.1, 1.4])
    principal_wan = left.number_input(
        '本金（萬元）', min_value=100.0, max_value=100000.0, step=100.0,
        value=float(PRESETS['退休5']['amount_wan']), key='retirement_principal_wan')
    # The preset comes first: this page exists to explain what the app actually does, and
    # the poster is captioned as the other ratio.
    shape = middle.radio('配置比例', [PRESET, ORIGINAL], key='retirement_shape',
                         help='APP 的退休5／退休6 用比較好記的 90：10；圖上畫的是原始的 100：12。')
    transfer_rate = right.slider(
        '每年從成長池撥出（%）', min_value=TRANSFER_RANGE[0], max_value=TRANSFER_RANGE[1],
        value=TRANSFER_RATE * 100, step=0.5, format='%.1f%%', key='retirement_transfer_rate',
        help='這是設計裡唯一決定「生活費水準」的數字，調動它整條收入曲線會跟著上下移。'
             '領出率固定在 25%，因為那決定的是平滑程度而不是水準。') / 100
    share = growth_share(shape)
    plan = pool_plan(principal_wan * 10000, share, transfer_rate)

    cards = st.columns(4)
    _caption(cards[0], '成長池', wan(plan['growth']), f'{share:.1%}')
    _caption(cards[1], '緩衝池', wan(plan['buffer']), f'{1 - share:.1%}')
    _caption(cards[2], '首年生活費', wan(plan['spend']), f'佔本金 {plan["spend_rate"]:.3%}')
    _caption(cards[3], '平均每月', wan(plan['monthly']), '總額 ÷ 12，未計稅與費用')

    kept = 1 - transfer_rate
    st.markdown(
        '| 步驟 | 算式 | 結果 |\n|---|---|---|\n'
        f'| 成長池撥出 | {wan(plan["growth"])} × {transfer_rate:.1%} | {wan(plan["transfer"])} |\n'
        f'| 撥入後的緩衝池 | {wan(plan["buffer"])} ＋ {wan(plan["transfer"])} | {wan(plan["pooled"])} |\n'
        f'| 今年生活費 | {wan(plan["pooled"])} × {WITHDRAW_RATE:.0%} | **{wan(plan["spend"])}** |\n'
        f'| 留在緩衝池 | {wan(plan["pooled"])} × {1 - WITHDRAW_RATE:.0%} | {wan(plan["buffer_left"])} |\n'
        f'| 留在成長池 | {wan(plan["growth"])} × {kept:.1%} | {wan(plan["growth_left"])} |\n')
    st.caption(f'緩衝池的存量相當於 {plan["buffer_years"]:.2f} 年的生活費。')

    # The balance is a property of 4% against a three-year buffer, not of the rule, so a
    # moved slider has to say which way it now leans rather than let the table imply it holds.
    if plan['spend'] > plan['transfer'] * 1.001:
        st.warning(f'**撥出率調到 {transfer_rate:.1%} 之後，領出的錢多過撥入的錢**'
                   f'（{wan(plan["spend"])} vs {wan(plan["transfer"])}）。'
                   '緩衝池會逐年變薄，平滑的能力跟著變弱；生活費一開始比較高，'
                   '但這是把緩衝挪去花掉換來的。')
    elif plan['transfer'] > plan['spend'] * 1.001:
        st.caption(f'撥出 {wan(plan["transfer"])}、領出 {wan(plan["spend"])}，'
                   '撥入多過領出，緩衝池會慢慢變厚。')

    _render_backtest(principal_wan * 10000, share, transfer_rate)

    st.markdown('### 想看細節的話')
    with st.expander('一年只做哪兩個動作'):
        st.markdown(
            f'1. **從成長池撥出當時市值的 {transfer_rate:.1%}**，放進緩衝池。'
            f'剩下的 {kept:.1%} 繼續投資，不動。\n'
            f'2. **從緩衝池領出 {WITHDRAW_RATE:.0%}** 當今年的生活費 —— 這一步決定的是'
            '**今年的總額**，不是非得一次領完（見「執行面」）。'
            f'剩下的 {1 - WITHDRAW_RATE:.0%} 留著，繼續當緩衝。')

    with st.expander('執行面：金額一年決定一次，動用可以分月'):
        gain = monthly_execution_gain(plan['spend'])
        st.markdown(
            '**撥款是一年一次的動作。** 在那一天用當時的市值算出撥出額與今年的生活費總額，'
            '算完就固定了，接下來一整年不再隨市場變動。\n\n'
            '**但「領出來」不必一次領完。** 把總額分成十二份逐月動用，效果是一樣的，'
            '而且還沒動用的部分留在緩衝池裡繼續生息。以 00865B 實測年化 2.89% 估，'
            f'分月動用比年初一次領出大約多 **{wan(gain)}**／年'
            f'（約等於生活費的 {gain / plan["spend"]:.1%}）—— 金額不大，但方向對你有利。\n\n'
            '**上面那張回測圖跑的就是分月動用**，所以它已經含進這個好處；'
            'WORKLOG 裡引用的四十年模擬則是年初一次扣掉，因此比實際保守一點。')
        st.warning('**分月動用不等於每月重算。** 每個月只是把年初算好的總額取出十二分之一；'
                   '若改成每個月重新計算一次「緩衝池的 25%」，那是完全不同的規則 —— '
                   '一年會領走緩衝池的 96.8%（1 − 0.75¹²），緩衝立刻消失。'
                   '**25% 是年度比率，不是月度比率。**')

    with st.expander('每個數字為什麼是那個數字'):
        st.markdown(
            '**4% —— 撥出率，決定生活費的水準。** 它不是報酬率，也不是「安全提領率」，'
            '而是你每年從成長池搬多少到花得到的地方。這個數字調高，生活費整條曲線往上移；'
            '但調到 7% 就會出現吃本金的訊號 —— 模擬裡第 40 年的收入反而低於第 20 年。'
            '**上面的滑桿可以直接把它改掉，看同一段歷史會變成什麼樣子。**\n\n'
            '**25% —— 領出比例，也就是四分之一。** 領四分之一的意思是，緩衝池裡的每一塊錢'
            '平均要花四年。這是把「今年市場的好壞」攤開到好幾年的動作，也是整個設計的核心。\n\n'
            '**12 ÷ 4 ＝ 3 —— 緩衝池正好是三年的提領量，這就是 100：12 的由來。**'
            '三年是典型的緩衝設計：足以撐過一次常見的空頭，又不至於放太多錢在低報酬的短債上。\n\n'
            '**這個組合讓第一年進出剛好打平，不是巧合。** 緩衝池 12 份加上今年撥入的 4 份等於 16 份，'
            '取 25% 正好是 4 份 —— 等於撥入量。寫成代數就是 **（G × 4% ＋ B）× 25% ≡ G × 4%**，'
            '在 B 等於三倍撥出量時成立。所以緩衝池不會被自己的規則慢慢抽乾。'
            '**這個等式只在 4% 配三年緩衝時成立**，滑桿一動它就不再平衡。\n\n'
            '**留下 75% 帶來的平滑，才是緩衝池真正在做的事。** 忽略短債報酬與費用，'
            '整條規則可以化簡成一句話：\n\n'
            '> **今年生活費 ＝ 去年生活費 × 75% ＋ 今年撥款 × 25%**\n\n'
            '今年的市場只影響生活費的四分之一。成長池由 100 跌到 60、緩衝池維持 12，'
            '生活費從 4 降到 3.6 —— **股票跌 40%，生活費只降 10%。**')

    with st.expander('為什麼不需要再平衡'):
        st.markdown(
            '這個規則會自己把兩個池子的比例拉回原位。令 B ÷ G ＝ x，均衡點是\n\n'
            '> x ＝ 0.04k ÷ (1 − k)，其中 k ＝ 0.75(1 ＋ r_b) ÷ 0.96(1 ＋ r_g)\n\n'
            '代入實測報酬（世界股票 9.5%、美短債 2.8%）得 x ≈ 0.110，'
            '也就是**緩衝池會穩定在總資產的一成左右**。模擬四十年的中位數是'
            ' 10.36 ／ 10.24 ／ 10.31 ／ 10.24%（第 1／10／20／40 年）—— **四十年不漂移**。\n\n'
            '2008 那一段最能看出它的性格。下面是緩衝池佔總資產的比例逐年變化：\n\n'
            '`10.0 → 9.9 → 10.0 → 10.9 → 17.9 → 12.5 → 11.0 → 11.5 → 11.0 → 10.1`\n\n'
            '崩盤時分母縮水，佔比自動跳到 17.9%（**在最該保守的時候自動保守**）；'
            '兩三年後又自動回到一成（**在最該加碼的時候自動加碼**）。全程零額外交易。')

    with st.expander('這個設計買到了什麼'):
        st.markdown(
            '| 項目 | 緩衝池法 | 對照 |\n|---|---|---|\n'
            '| 最差的單年收入 | **−12.9%** | 沒有緩衝池：−37.1% |\n'
            '| 組合存續期間 | **0.21 年** | 退休1（含長債）：7.00 年 |\n'
            '| 2022 股債同跌 | **−9.8%** | 退休1：−16.6% |\n'
            '| 需要質押借款 | **零** | 退休1：每年約 56 萬 |\n'
            '| 通膨 5% 下第 40 年實質收入 | 334 萬（2% 時 339 萬） | 退休1 斷頭機率 5.1% → 19.0% |\n')
        st.caption('最差單年收入那兩欄是同樣資產、同樣提領率，只差有沒有緩衝池。'
                   '存續期間短代表升息造成的帳面損失小 —— 這一項與抗通膨其實是同一個曝險的兩面。'
                   '這些數字出自 WORKLOG 第四十、四十一次的四十年模擬，'
                   '用的是歷史代理序列，不是上面那張 6.8 年回測圖。')

    with st.expander('策略說明圖（原始設計 100：12）'):
        if POSTER.exists():
            st.image(str(POSTER),
                     caption='策略說明圖：原始設計 100：12（出自 analysis/，不是 APP 預設的 90：10）')
        else:
            st.info('策略說明圖不在預期位置（`analysis/retirement5-original-100-12.png`）。'
                    '上面的文字與試算不受影響。')
