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

from allocation import BUFFER_PRESETS, PRESETS
from ui import wan

# The withdrawal rate stays a constant: a quarter is what spreads one year's market over
# four, and the whole page is an explanation of that. The transfer rate is adjustable
# because it is the one that sets the level of the income rather than its smoothness, and
# seeing what a different one does to the same history is the point of asking.
TRANSFER_RATE = 0.04   # moved out of the growth pool each year
WITHDRAW_RATE = 0.25   # taken out of the buffer each year, i.e. a quarter
TRANSFER_RANGE = (1.0, 8.0)
# January, because a date a reader can remember is worth more than one that happens to
# fall where the data starts. The rule does not care which month it is -- it only cares
# that it is the same one every year.
TRANSFER_MONTH_OF_YEAR = 1

# 00865B's measured return over its 6.8 years, from WORKLOG 第四十次. Only used to price
# the difference between taking the year's money out at once and taking it monthly.
BUFFER_YIELD = 0.0289
# Draw a twelfth at the start of each month and the money still in the pool earns, on
# average, 11/24 of a year that a lump sum at the start of the year would have missed.
HELD_FRACTION = 11 / 24

# The poster is the study's own artwork and stays with the study it came from.
POSTER = Path(__file__).resolve().parent.parent / 'analysis' / 'retirement5-original-100-12.png'

ORIGINAL = '原始設計 100：12'
PRESET = 'APP 預設 90：10'

# Every preset that is this rule gets offered here, including the one a reader would
# actually hold and that has no history to run: 009826 listed in July 2026. The others
# differ from it, and from each other, in the growth pool and nothing else -- and they
# share the buffer, so they land on the same window and can be read against each other.
# The set is the sidebar's, so the mark on the dropdown and the choices here cannot
# come apart.
BACKTEST_PRESETS = BUFFER_PRESETS
BACKTEST_DEFAULT = '退休6'
BACKTEST_FROM = date(2008, 1, 1)

# The buffer is a specific fund, not "whichever holding is smallest". Naming it is what
# lets a growth pool hold more than one thing: 退休8 splits its 90% across two, and the
# smallest-weight rule would have called one of those the buffer.
BUFFER_SYMBOL = '00865B.TW'

# What a reader has to know about the holding they just picked. Kept beside the choice
# rather than in a footnote: the numbers underneath change completely with it.
BACKTEST_NOTES = {
    '退休5': ('**這是真的要持有的配置**，但 009826 於 2026-07-22 才上市，'
             '沒有足夠長的歷史可以跑這條規則 —— 其餘幾個就是為此存在的替身。'),
    '退休6': ('成長池是**全世界股票**（VT），以美元計價、自動換算台幣，'
             '所以報酬含匯率變動。這是退休5 在資產類別上最接近的替身。'),
    '退休7': ('成長池是**台股**（0050）。它跑出來的數字會比退休6 好很多，'
             '但那是**單一市場、而且超過一半集中在台積電**的結果 —— '
             '起始就有整體一成半以上押在同一家公司。'
             '而這段期間正好是台積電與 AI 的超級循環：'
             '專案內另一份量測（2006-06 至 2026-08）是台股年化 13.68%、全球 8.48%，'
             '**那個差距是這段歷史的結果，不是可以外推的前提**。'
             '真正看不到的風險是同向性：台海若出事，台股與台幣會一起重挫，'
             '而以台幣計價的世界股票反而會因台幣貶值而上漲 —— '
             '**那個情境在這段樣本裡一次都沒發生過。**'),
    '退休8': ('成長池是**兩檔**：0050（台股）50% ＋ 00662（那斯達克100）40%，'
             '每年各提 4% 到緩衝池。**兩檔的月報酬相關 0.59**，'
             '所以這是真的有分散效果，不是同一個賭注的兩種寫法 —— '
             '回撤也確實比純台股淺（實測 −27.4% 對 −32.0%）。\n\n'
             '**但兩檔押的是同一個主題。** 0050 超過一半是台積電，00662 是美國大型科技股，'
             '而這段期間是半導體與 AI 的超級循環，兩邊都吃到同一波。'
             '**成長池內部沒有再平衡**：實測 0050 佔成長池的比例由 55.6% 漂到 66.5%，'
             '所以「50：40」是起始條件，不是長期會維持的東西 —— '
             '這與第四十六次評估「成長池拆成世界＋台股」時記下的同一個問題。'),
}


def pool_split(preset):
    """A preset's growth holdings and their weights, and the buffer's weight.

    Everything that is not the buffer is the growth pool, however many holdings that is.
    """
    weights = PRESETS[preset]['weights']
    growth = {symbol: weight for symbol, weight in weights.items() if symbol != BUFFER_SYMBOL}
    return growth, weights.get(BUFFER_SYMBOL, 0.0)


def growth_share(shape, preset='退休5'):
    """The growth pool's share of the whole, read off the preset rather than restated here.

    `preset` so the backtest follows whichever one is being run. Summed over the growth
    holdings, not taken from the largest: 退休8's pool is 50 ＋ 40, and the largest alone
    would call that a 50% growth pool.
    """
    if shape == ORIGINAL:
        return 100 / 112
    growth, buffer = pool_split(preset)
    return sum(growth.values()) / (sum(growth.values()) + buffer)


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


# What each holding is, in the words the diagram prints under its code, and which currency
# a NT$ holder is exposed to through it. Only 0050 is a Taiwan asset: the others are listed
# here or trade in dollars, but hold foreign assets unhedged, so they move with the dollar.
HOLDING_NAMES = {'0050.TW': '台灣50', '00662.TW': '那斯達克100', 'VT': '全世界股票',
                 '009826.TW': '世界股票', BUFFER_SYMBOL: '美國短債'}
TWD_HOLDINGS = {'0050.TW'}

_DIAGRAM_CSS = """<style>
.rp{--g:#3E9C86;--b:#D2963F;--w:#7F9BBA;--twd:#C8604E;--usd:#4F7FB5;
  --ln:rgba(128,128,128,.28);--soft:rgba(128,128,128,.08);font-size:14px;line-height:1.6;margin:4px 0 8px}
.rp .flow{display:grid;grid-template-columns:1.3fr auto 1fr auto .9fr;align-items:stretch}
.rp .node{border:1px solid var(--ln);border-radius:12px;padding:14px 16px;display:grid;gap:8px;align-content:start}
.rp .node.g{border-top:4px solid var(--g)} .rp .node.b{border-top:4px solid var(--b)} .rp .node.w{border-top:4px solid var(--w)}
.rp .t{font-weight:700;font-size:17px} .rp .t span{font-weight:400;font-size:13px;opacity:.65;margin-left:6px}
.rp .amt{font-size:26px;font-weight:700;line-height:1.15;font-variant-numeric:tabular-nums}
.rp .g .amt{color:var(--g)} .rp .b .amt{color:var(--b)} .rp .w .amt{color:var(--w)}
.rp .amt small{font-size:13px;font-weight:400;opacity:.7;margin-left:3px}
.rp .h{display:flex;gap:8px;align-items:center;justify-content:space-between;background:var(--soft);
  border-radius:7px;padding:5px 9px;font-size:13px}
.rp .h span:first-child{flex:1;min-width:0}
.rp .h b{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.rp .cur{font-size:11px;font-weight:700;padding:0 7px;border-radius:99px;color:#fff;white-space:nowrap}
.rp .cur.twd{background:var(--twd)} .rp .cur.usd{background:var(--usd)}
.rp .role{font-size:12.5px;opacity:.7;margin:0}
.rp .arr{display:grid;justify-items:center;align-content:center;gap:2px;padding:0 10px;min-width:104px;text-align:center}
.rp .arr .k{font-size:11.5px;opacity:.65;letter-spacing:.06em}
.rp .arr .v{font-weight:700;font-size:15px} .rp .a1 .v{color:var(--g)} .rp .a2 .v{color:var(--b)}
.rp .arr .n{font-size:12.5px;opacity:.7;font-variant-numeric:tabular-nums}
.rp .arr .line{width:100%;height:0;border-top:1.6px solid currentColor;position:relative;margin:4px 0}
.rp .arr .line::after{content:"";position:absolute;right:-2px;top:-6px;border:5.5px solid transparent;border-left:9px solid currentColor;border-right:0}
.rp .fx{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
.rp .panel{border:1px solid var(--ln);border-radius:12px;padding:12px 16px;display:grid;gap:8px;align-content:start}
.rp .panel .pt{font-weight:700;font-size:14px}
.rp .panel p{margin:0;font-size:12.5px;opacity:.75}
.rp .bar{display:flex;height:28px;border-radius:7px;overflow:hidden;font-size:12px;font-weight:700;color:#fff}
.rp .bar span{display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden}
.rp .bar .twd{background:var(--twd)} .rp .bar .usd{background:var(--usd)}
.rp .months{display:grid;grid-template-columns:repeat(12,1fr);gap:3px}
.rp .months i{height:24px;border-radius:4px;background:var(--soft);border-bottom:3px solid var(--b);
  font-style:normal;font-size:10.5px;opacity:.85;display:grid;place-items:center}
.rp .note{font-size:12.5px;opacity:.7;margin:10px 0 0}
@media (max-width:760px){
  .rp .flow{grid-template-columns:1fr}
  .rp .arr{padding:8px 0}
  .rp .arr .line{width:0;height:26px;border-top:0;border-left:1.6px solid currentColor}
  .rp .arr .line::after{right:auto;left:-6px;top:auto;bottom:-2px;border:5.5px solid transparent;border-top:9px solid currentColor;border-bottom:0}
  .rp .fx{grid-template-columns:1fr}
}
</style>"""


def currency_mix(preset):
    """The NT$ and US$ shares of a preset, read off its weights and TWD_HOLDINGS."""
    weights = PRESETS[preset]['weights']
    twd = sum(w for s, w in weights.items() if s in TWD_HOLDINGS) / sum(weights.values())
    return twd, 1 - twd


def _w(value):
    """wan(), falling back to whole NT$ below one 萬 so a small principal still reads."""
    return wan(value) or f'{value:,.0f} 元'


def pool_diagram(plan, preset, transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """The rule on one picture: two pools, the two yearly rates between them, the wallet.

    Built from `plan` so every figure on it is the calculator's, and from `preset` so the
    holdings and the currency split are the ones being run below it.
    """
    growth, buffer_weight = pool_split(preset)

    def holding(symbol, weight_text):
        cur = 'twd' if symbol in TWD_HOLDINGS else 'usd'
        return (f'<div class="h"><span>{symbol.removesuffix(".TW")} {HOLDING_NAMES.get(symbol, "")}</span>'
                f'<b>{weight_text}</b><span class="cur {cur}">{"台幣" if cur == "twd" else "美元"}</span></div>')

    # Shares of the whole, as the preset writes them: 退休8 reads 50 and 40, not 56 and 44.
    growth_rows = ''.join(holding(s, f'{w:.0f}%')
                          for s, w in sorted(growth.items(), key=lambda i: -i[1]))
    twd, usd = currency_mix(preset)
    bar = ''.join(f'<span class="{c}" style="width:{v:.1%}">{label} {v:.0%}</span>'
                  for c, label, v in (('twd', '台幣', twd), ('usd', '美元', usd)) if v > 0.005)
    if twd > 0.005:
        mix_note = ('台幣升值時，台幣資產不受影響；股災時美元通常走強，美元資產撐住。'
                    '兩種貨幣都有，哪個方向都不會全押。')
    else:
        mix_note = ('這個配置全部是未避險的美元資產：股災時美元通常走強，但台幣升值時'
                    '兩個池子會一起縮水。')
    months = ''.join(f'<i>{m}</i>' for m in range(1, 13))
    return (_DIAGRAM_CSS + '<div class="rp">'
            '<div class="flow">'
            f'<div class="node g"><div class="t">成長池<span>{plan["growth"] / (plan["growth"] + plan["buffer"]):.0%}</span></div>'
            f'<div class="amt">{_w(plan["growth"])}</div>{growth_rows}'
            '<p class="role">負責長大。不再平衡，讓它自己長。</p></div>'
            f'<div class="arr a1"><div class="k">每年 1 月</div><div class="v">撥出 {transfer_rate:.1%}</div>'
            f'<div class="line"></div><div class="n">{_w(plan["transfer"])}</div></div>'
            f'<div class="node b"><div class="t">緩衝池<span>{plan["buffer"] / (plan["growth"] + plan["buffer"]):.0%}</span></div>'
            f'<div class="amt">{_w(plan["buffer"])}<small>→ {_w(plan["pooled"])}</small></div>'
            f'{holding(BUFFER_SYMBOL, f"{buffer_weight:.0f}%")}'
            '<p class="role">負責發錢。收到撥款後，定出今年的生活費。</p></div>'
            f'<div class="arr a2"><div class="k">每年</div><div class="v">提領 {withdraw_rate:.0%}</div>'
            f'<div class="line"></div><div class="n">{_w(plan["spend"])}<br>每月 {_w(plan["monthly"])}</div></div>'
            f'<div class="node w"><div class="t">生活費</div>'
            f'<div class="amt">{_w(plan["spend"])}<small>／年</small></div>'
            '<p class="role">隨市場浮動，但一年只變一次；每月從緩衝池賣出十二分之一。</p></div>'
            '</div>'
            '<p class="note">只有這三個動作：不換定存、不挑時點、不再平衡。</p>'
            '<div class="fx">'
            f'<div class="panel"><div class="pt">匯率分散之一：資產上</div><div class="bar">{bar}</div>'
            f'<p>{mix_note}</p></div>'
            f'<div class="panel"><div class="pt">匯率分散之二：時間上</div><div class="months">{months}</div>'
            '<p>生活費每月換一次台幣，一年分散在 12 個匯率上，不押在同一天。</p></div>'
            '</div></div>')


def month_ends(growth_prices, buffer_prices):
    """The holdings on the days all of them traded, one row per calendar month.

    `growth_prices` is one series or a frame of several; the growth columns keep their own
    names, and a lone series becomes 'growth' so the single-holding case reads the same.
    Grouped by period rather than resampled: a resample invents a row for a month with no
    observation, and a NaN there would read as a month the pools were worth nothing.
    """
    frame = (growth_prices.to_frame('growth') if isinstance(growth_prices, pd.Series)
             else growth_prices)
    paired = frame.join(buffer_prices.rename('buffer'), how='inner').dropna(how='any')
    if paired.empty:
        return paired
    paired = paired.sort_index()
    monthly = paired.groupby(paired.index.to_period('M')).last()
    monthly.index = monthly.index.to_timestamp(how='end').normalize()
    return monthly


def growth_pool(prices, weights=None, since=None):
    """The growth pool's value path: bought at `weights` on its first day, never rebalanced.

    A pool of several holdings behaves exactly like one holding under this rule, and that
    is not an approximation: 4% out of each is 4% of the total, and because the rate is the
    same for all of them the split between them is left where the market put it. So the
    whole rule can run on this one series.

    `since` matters. The weights are opening weights, so they have to be applied on the day
    the run opens -- normalising earlier would start the pool at proportions the market had
    already moved away from.
    """
    frame = prices.to_frame('growth') if isinstance(prices, pd.Series) else prices
    frame = frame.dropna(how='any').sort_index()
    if since is not None:
        frame = frame.loc[frame.index >= since]
    if frame.empty:
        return pd.Series(dtype=float)
    share = (pd.Series(1.0, index=frame.columns) if weights is None
             else pd.Series(weights, dtype=float).reindex(frame.columns))
    if share.isna().any():
        raise ValueError(f'成長池比重缺少：{list(share[share.isna()].index)}')
    return frame.div(frame.iloc[0]).mul(share / share.sum(), axis=1).sum(axis=1)


def backtest(growth_prices, buffer_prices, principal, share,
             transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE, growth_weights=None):
    """Run the rule month by month over real prices, and record what it paid out.

    The year's amount is fixed once, every January, and then drawn a twelfth at a time --
    which is what the 執行面 section says to do, and leaves the rest of it earning in the
    buffer rather than sitting in a wallet. Both pools are marked to the month's close
    after the draw, so each row is an end-of-month position.

    `growth_prices` may be a frame of several holdings, with `growth_weights` giving their
    opening split; see growth_pool for why that needs no change to the rule itself.
    """
    monthly = month_ends(growth_prices, buffer_prices)
    # Begin on the first January there is. Starting wherever the data happens to open
    # would put two transfers inside one quarter and a stub year on the chart, for the
    # sake of keeping a couple of months nobody asked to see.
    opening = [i for i, when in enumerate(monthly.index)
               if when.month == TRANSFER_MONTH_OF_YEAR]
    if opening:
        monthly = monthly.iloc[opening[0]:]
    if len(monthly) < 13:
        raise ValueError(f'需要至少 13 個月、且涵蓋一個完整年度的共同行情，'
                         f'目前只有 {len(monthly)} 個月。')
    # Blended on the sliced frame, so the opening weights land on the month the run opens.
    pool = growth_pool(monthly.drop(columns='buffer'), growth_weights)
    growth_step = pool.pct_change().fillna(0.0)
    buffer_step = monthly['buffer'].pct_change().fillna(0.0)

    growth, buffer = principal * share, principal * (1 - share)
    annual = draw = 0.0
    rows = []
    for position, when in enumerate(monthly.index):
        moved = 0.0
        if when.month == TRANSFER_MONTH_OF_YEAR:
            moved = transfer = growth * transfer_rate
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
                     '總資產': growth + buffer, '當月生活費': spent,
                     '年生活費': annual, '當月撥款': moved,
                     '撥款月': when.month == TRANSFER_MONTH_OF_YEAR})
    return pd.DataFrame(rows).set_index('月份')


def yearly_income(run):
    """What each calendar year actually paid, indexed by the year itself.

    Only whole years: the history ends mid-year, and a group of nine months would read
    as the year the income collapsed. Calendar years rather than counted ones now that
    the transfer is every January -- '2025 年' beats '第 6 年' for anyone checking.
    """
    if run.empty:
        return pd.Series(dtype=float)
    by_year = run['當月生活費'].groupby(run.index.year)
    return by_year.sum()[by_year.count() == 12]


def _paired(growth, buffer):
    """One frame of a preset's holdings on the days all of them traded."""
    frame = growth.to_frame('growth') if isinstance(growth, pd.Series) else growth
    return frame.join(buffer.rename('buffer'), how='inner').dropna(how='any').sort_index()


def shared_window(prices):
    """The dates every one of these presets has all of its holdings priced on.

    Each preset run over its own window would reward whichever one happens to hold the
    youngest fund -- the 配置比較 page intersects its dates for the same reason. Today they
    all share the buffer so their windows already coincide; this is what keeps the
    comparison honest the day one of them does not.
    """
    common = None
    for growth, buffer in prices.values():
        paired = _paired(growth, buffer)
        if paired.empty:
            return None
        common = paired.index if common is None else common.intersection(paired.index)
    return common if common is not None and len(common) >= 2 else None


def compare_presets(pools, principal, share, transfer_rate=TRANSFER_RATE,
                    withdraw_rate=WITHDRAW_RATE):
    """One row per preset, every one of them run over the single window they all share.

    `pools` maps a name to `(growth_prices, buffer_prices, growth_weights)` -- growth being
    a frame when the pool holds more than one thing, and the weights coming from the caller
    rather than being looked up here, so this stays a function of its arguments.

    A preset whose history is too short to hold a year is left out rather than shown with a
    blank row: the reason it cannot run belongs next to the choice, not in a table of
    results.
    """
    # Drop a preset that cannot hold a year on its own history *before* intersecting.
    # Left in, 退休5's few weeks would shrink the shared window to those weeks and take
    # every other preset down with it -- a comparison of nothing against nothing.
    usable = {}
    for name, (growth, buffer, weights) in pools.items():
        try:
            backtest(growth, buffer, principal, share, transfer_rate, withdraw_rate,
                     growth_weights=weights)
        except ValueError:
            continue
        usable[name] = (growth, buffer, weights)
    window = shared_window({n: (g, b) for n, (g, b, _) in usable.items()})
    if window is None:
        return pd.DataFrame(), None
    rows, covered = {}, None
    for name, (growth, buffer, weights) in usable.items():
        try:
            run = backtest(growth.loc[window], buffer.loc[window], principal, share,
                           transfer_rate, withdraw_rate, growth_weights=weights)
        except ValueError:
            continue
        # What the runs cover, not the raw overlap: they all start at the same first
        # January, and quoting the data's first day would name months nobody ran.
        covered = (run.index[0], run.index[-1])
        paid = yearly_income(run)
        if paid.empty:
            continue
        falls = paid.pct_change().dropna()
        rows[name] = {
            '成長池': pool_label(growth, weights),
            '首年生活費': float(paid.iloc[0]),
            '末年': int(paid.index[-1]),
            '末年生活費': float(paid.iloc[-1]),
            '最差單年變化': float(falls.min()) if len(falls) else float('nan'),
            '期末總資產': float(run['總資產'].iloc[-1]),
            '成長池最大回撤': float((run['成長池'] / run['成長池'].cummax() - 1).min()),
            '期末緩衝池佔比': float(run['緩衝池'].iloc[-1] / run['總資產'].iloc[-1]),
        }
    if not rows:
        return pd.DataFrame(), None
    return pd.DataFrame(rows).T, covered


def pool_label(growth, weights=None):
    """What the growth pool holds, heaviest first, for a table cell."""
    if weights:
        ordered = sorted(weights.items(), key=lambda pair: -pair[1])
        return '＋'.join(f'{symbol.split(".")[0]} {weight:.0f}%' for symbol, weight in ordered)
    columns = [growth.name] if isinstance(growth, pd.Series) else list(growth.columns)
    return '＋'.join(str(column).split('.')[0] for column in columns)


# Two readings on one picture, so they need to stay apart: the money you live on, and what
# it is coming out of. Gold is the income because that is the line a reader is here for.
INCOME_COLOUR = '#F5C451'
# The anniversary is the only month anything is decided; the eleven after it just pay
# out what it decided. Same height, different colour -- it marks when, not how much.
TRANSFER_COLOUR = '#D0A2FF'
ORDINARY_MONTH = '一般月份（照年初算好的領）'
TRANSFER_MONTH = '撥款月（重算今年金額）'
ASSET_COLOUR = '#35CDBF'


def backtest_holdings(preset=BACKTEST_DEFAULT):
    """The growth pool's symbols, heaviest first, and the buffer's."""
    growth, _ = pool_split(preset)
    return tuple(sorted(growth, key=growth.get, reverse=True)), BUFFER_SYMBOL


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def backtest_prices(today, preset=BACKTEST_DEFAULT):
    """One preset's holdings, over everything they have. `today` keys the cache.

    The growth pool comes back as a frame, one column per holding, so the blend can be
    struck on the day the run opens rather than here.
    """
    from market import load_frame
    growth_symbols, buffer_symbol = backtest_holdings(preset)
    histories, failures, _, _ = load_frame(list(growth_symbols) + [buffer_symbol],
                                           BACKTEST_FROM, today, 'Adj Close')
    if failures:
        raise ValueError('、'.join(f'{s}：{why[:100]}' for s, why in failures.items()))
    growth = pd.concat({s: histories[s] for s in growth_symbols}, axis=1)
    return growth, histories[buffer_symbol]


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
    frame['當月撥款（萬）'] = frame['當月撥款'] / 10000
    frame['月份類型'] = [TRANSFER_MONTH if flag else ORDINARY_MONTH
                         for flag in frame['撥款月']]
    when = alt.X('月份:T', title=None, axis=alt.Axis(format='%Y', tickCount='year'))
    tooltip = [alt.Tooltip('月份:T', format='%Y/%m'),
               alt.Tooltip('每月生活費（萬）:Q', format='.2f'),
               alt.Tooltip('總資產（萬）:Q', format=',.0f'),
               alt.Tooltip('成長池（萬）:Q', format=',.0f'),
               alt.Tooltip('緩衝池（萬）:Q', format=',.0f'),
               alt.Tooltip('當月撥款（萬）:Q', format=',.1f')]
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
    layers.append(alt.Chart(frame).mark_bar(opacity=.9).encode(
        x=when, y=alt.Y('每月生活費（萬）:Q', title='每月生活費（萬元）',
                        axis=alt.Axis(titleColor=INCOME_COLOUR, labelColor=INCOME_COLOUR)),
        color=alt.Color('月份類型:N', title=None,
                        scale=alt.Scale(domain=[ORDINARY_MONTH, TRANSFER_MONTH],
                                        range=[INCOME_COLOUR, TRANSFER_COLOUR]),
                        legend=alt.Legend(orient='bottom')),
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


def _render_backtest(principal, shape, transfer_rate, preset=BACKTEST_DEFAULT):
    st.markdown(f'### {preset} 走過真實行情')
    growth_symbols, buffer_symbol = backtest_holdings(preset)
    growth_weights, _ = pool_split(preset)
    share = growth_share(shape, preset)
    pool_text = '＋'.join(f'{s} {growth_weights[s]:.0f}%' for s in growth_symbols)
    note = BACKTEST_NOTES.get(preset)
    if note:
        with st.expander(f'讀這段回測之前：{preset} 的成長池'):
            st.markdown(note)
    prices = None
    try:
        prices = backtest_prices(datetime.now(ZoneInfo('Asia/Taipei')).date(), preset)
        growth_prices, buffer_prices = prices
        run = backtest(growth_prices, buffer_prices, principal, share, transfer_rate,
                       growth_weights=growth_weights)
    except Exception as exc:
        st.warning(f'**{preset} 無法回測：**{exc}')
        # Name the day the overlap starts, not just how many months it is: with these presets
        # the answer is almost always "the growth pool has not existed long enough", which is
        # the whole reason the other ones are on the list at all.
        if prices is not None:
            overlap = _paired(prices[0], prices[1])
            if len(overlap):
                span = (overlap.index[-1] - overlap.index[0]).days / 365.25
                st.caption('、'.join(growth_symbols) + f' 與 {buffer_symbol} 只在 '
                           f'{overlap.index[0]:%Y/%m/%d} 之後同時有行情，'
                           f'到 {overlap.index[-1]:%Y/%m/%d} 共 {span:.2f} 年。')
        st.caption('上面的圖不受影響，它不需要行情。想看回測，改選其他有夠長歷史的配置。')
        return

    first, last = run.index[0], run.index[-1]
    years = (last - first).days / 365.25
    st.caption(f'{pool_text} 成長池 ＋ {buffer_symbol} 緩衝池 · '
               f'{first:%Y/%m} — {last:%Y/%m}（{years:.1f} 年，{len(run)} 個月）· '
               f'起始 {wan(principal)} · 撥出率 {transfer_rate:.1%}、領出率 {WITHDRAW_RATE:.0%}')
    # Daily, and only over the window every holding has. Month ends would have called COVID
    # a 22.3% fall when it was 33.6% and lost the 2025 one entirely; the growth pool's own
    # history reaches back further than the buffer's, which is time this chart knows nothing
    # about. The shading is a span of dates either way.
    common = _paired(growth_prices, buffer_prices).loc[run.index[0]:]
    # The pool's own falls, not one holding's: with two holdings neither of them is the
    # thing the rule draws from, and the blend is what the income actually came out of.
    pool_daily = growth_pool(common.drop(columns='buffer'), growth_weights)
    episodes = drawdown_episodes(pool_daily)
    st.altair_chart(income_chart(run, episodes), width='stretch')
    st.caption('**金色長條**：每月生活費，一年一階。**紫色長條**：每年 1 月撥款、重算生活費的那個月。'
               '**青綠色線**：總資產（右軸），已扣掉領走的錢。'
               f'**紅色區塊**：成長池跌超過 {SHADE_DEEPER_THAN:.0%}，由高點到收復。')

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
                         f'{len(episodes)} 次）'):
            st.markdown(chr(10).join(rows))
            st.caption('日期與跌幅由行情算出；事件名稱是一般市場認知，認不出的留白。'
                       '**「同期緩衝池」是關鍵**：它撐住了，生活費才撐得住。')

    paid = yearly_income(run)
    cards = st.columns(4)
    _caption(cards[0], '期末總資產', wan(run['總資產'].iloc[-1]),
             f'起始 {wan(principal)}')
    _caption(cards[1], '首年生活費', wan(paid.iloc[0]) if len(paid) else '—',
             f'每月約 {wan(paid.iloc[0] / 12)}' if len(paid) else '')
    if len(paid) > 1:
        change = paid.iloc[-1] / paid.iloc[0] - 1
        _caption(cards[2], f'{paid.index[-1]} 年生活費', wan(paid.iloc[-1]),
                 f'較首年 {change:+.1%}（名目，未計通膨）')
        worst = (paid.pct_change().dropna().min())
        _caption(cards[3], '最差的單年變化', f'{worst:+.1%}',
                 '同期成長池最大月底回撤 '
                 f'{(run["成長池"] / run["成長池"].cummax() - 1).min():.1%}')

    # Two pages report a total for the same preset and they differ by a lot. This one has
    # been paying out for the whole run; 投資報酬 never takes anything out, and its window
    # follows the sidebar rather than the data. Neither figure is wrong and nothing else on
    # either page says so, so the reconciliation goes next to the number people compare.
    spent = float(run['當月生活費'].sum())
    st.caption(f'**期末總資產是領走生活費之後的餘額。** 累計領了 '
               f'**{wan(spent) or f"{spent:,.0f} 元"}**，連同領走的合計 '
               f'**{wan(run["總資產"].iloc[-1] + spent)}**。'
               '「投資報酬」分頁算的是買進持有、一毛不提，期間也跟著側邊欄走，兩頁不能直接對照。')

    # The "為什麼不需要再平衡" section says the buffer settles near a tenth. It does -- at the
    # return gap that algebra was solved for. A faster growth pool dilutes it, and that is
    # measurable right here, so it gets said next to the number rather than left to contradict
    # the expander further down the page.
    share_now = run['緩衝池'].iloc[-1] / run['總資產'].iloc[-1]
    st.caption(f'期末緩衝池佔總資產 **{share_now:.1%}**（起始 {1 - share:.1%}）：'
               '成長池跑得越快，緩衝池被稀釋得越薄（見下方「為什麼不需要再平衡」）。')
    # A slider nobody can compare against is just a number that moves. Same history, same
    # principal, only the rate different -- that is the whole question being asked.
    if abs(transfer_rate - TRANSFER_RATE) > 1e-9:
        try:
            baseline = backtest(growth_prices, buffer_prices, principal, share,
                                TRANSFER_RATE, growth_weights=growth_weights)
        except ValueError:
            baseline = None
        if baseline is not None:
            base_paid = yearly_income(baseline)
            st.markdown(
                f'#### 撥出率 {transfer_rate:.1%} 對上預設的 {TRANSFER_RATE:.1%}\n\n'
                '| 同一段歷史、同一筆本金 | '
                f'{TRANSFER_RATE:.1%}（預設） | {transfer_rate:.1%}（你設的） |\n|---|---|---|\n'
                f'| 首年生活費 | {wan(base_paid.iloc[0])} | **{wan(paid.iloc[0])}** |\n'
                f'| {paid.index[-1]} 年生活費 | {wan(base_paid.iloc[-1])} | **{wan(paid.iloc[-1])}** |\n'
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
        st.caption(
            f'**緩衝池自己也跌過 {abs(currency["跌幅"]):.1%}**'
            f'（{currency["高點"]:%Y/%m} → {currency["谷底"]:%Y/%m}），'
            f'同期用美元計價是 {currency["美元計價"]:+.1%}：那是台幣升值，不是債券跌。'
            '這就是上面「匯率分散」在處理的風險。')

    st.caption(f'**這是一段 {years:.1f} 年的歷史，不是長期驗證**：受 {buffer_symbol} 上市日限制，'
               '只涵蓋 2020 急跌與 2022 股債同跌，沒有完整的長空頭。未計稅、費用與交易成本。')


def _render_comparison(principal, shape, transfer_rate):
    """Every preset that can run, side by side on the one window they all have.

    Switching the radio back and forth and remembering the numbers is not a comparison.
    The point of putting them in one table is that the column which wins on income is the
    same column that loses on drawdown, and that only shows when they are next to each other.
    """
    pools, unavailable = {}, []
    today = datetime.now(ZoneInfo('Asia/Taipei')).date()
    for name in BACKTEST_PRESETS:
        try:
            growth, buffer = backtest_prices(today, name)
        except Exception:
            unavailable.append(name)
            continue
        pools[name] = (growth, buffer, pool_split(name)[0])
    share = growth_share(shape)
    frame, window = compare_presets(pools, principal, share, transfer_rate)
    if len(frame) < 2:
        return
    # Fetched but dropped counts as left out too -- 退休5 arrives fine and is then
    # too short to run, which is the case a reader is most likely to ask about.
    left_out = unavailable + [n for n in pools if n not in frame.index]

    st.markdown('#### 並排比較')
    columns = list(frame.index)
    head = '| 同一段期間、同一筆本金 | ' + ' | '.join(columns) + ' |'
    rule = '|---' * (len(columns) + 1) + '|'
    def row(label, render):
        return f'| {label} | ' + ' | '.join(render(frame.loc[c]) for c in columns) + ' |'
    last_year = int(frame['末年'].max())
    st.markdown('\n'.join([
        head, rule,
        row('成長池', lambda r: f"`{r['成長池']}`"),
        row('首年生活費', lambda r: wan(r['首年生活費'])),
        row(f'{last_year} 年生活費', lambda r: wan(r['末年生活費'])),
        row('最差的單年變化', lambda r: f"{r['最差單年變化']:+.1%}"),
        row('期末總資產', lambda r: wan(r['期末總資產'])),
        row('成長池最大月底回撤', lambda r: f"{r['成長池最大回撤']:.1%}"),
        row('期末緩衝池佔比', lambda r: f"{r['期末緩衝池佔比']:.1%}"),
    ]))
    st.caption(
        f'期間 {window[0]:%Y/%m/%d} — {window[1]:%Y/%m/%d}（各配置都有行情的交集），'
        f'撥出率 {transfer_rate:.1%}，起始 {wan(principal)}。'
        + (f'{"、".join(left_out)} 歷史不足一年，未納入。' if left_out else '')
        + '**收入贏的那一欄，回撤也是輸的那一欄**；報酬差距是這段歷史的結果。')


def render_strategy():
    st.subheader('緩衝池退休法：成長池 ＋ 緩衝池')
    st.markdown(
        '**每年領走資產的一個比例，而不是固定金額**，所以在定義上不會把錢領到見底；'
        '代價是收入跟著市場上下，緩衝池的工作就是把那個上下壓平。')

    # The preset leads because the picture below it names the holdings and their currency,
    # and the backtest further down runs the same one -- one choice, not two that can differ.
    preset = st.radio(
        '配置', BACKTEST_PRESETS, index=BACKTEST_PRESETS.index(BACKTEST_DEFAULT),
        horizontal=True, key='retirement_backtest_preset',
        help='都是同一條規則、同樣 90：10，只差成長池裝什麼。緩衝池是同一檔 00865B。')
    left, middle, right = st.columns([1.1, 1.1, 1.4])
    principal_wan = left.number_input(
        '本金（萬元）', min_value=100.0, max_value=100000.0, step=100.0,
        value=float(PRESETS['退休5']['amount_wan']), key='retirement_principal_wan')
    # The preset comes first: this page exists to explain what the app actually does, and
    # the poster is captioned as the other ratio.
    shape = middle.radio('配置比例', [PRESET, ORIGINAL], key='retirement_shape',
                         help='APP 的預設用比較好記的 90：10；原始設計是 100：12。')
    transfer_rate = right.slider(
        '每年從成長池撥出（%）', min_value=TRANSFER_RANGE[0], max_value=TRANSFER_RANGE[1],
        value=TRANSFER_RATE * 100, step=0.5, format='%.1f%%', key='retirement_transfer_rate',
        help='決定生活費水準的數字。領出率固定在 25%，它決定的是平滑程度而不是水準。') / 100
    share = growth_share(shape, preset)
    plan = pool_plan(principal_wan * 10000, share, transfer_rate)
    st.html(pool_diagram(plan, preset, transfer_rate))

    # The balance is a property of 4% against a three-year buffer, not of the rule, so a
    # moved slider has to say which way it now leans rather than let the picture imply it holds.
    if plan['spend'] > plan['transfer'] * 1.001:
        st.warning(f'**撥出率 {transfer_rate:.1%} 時，領出多過撥入**'
                   f'（{_w(plan["spend"])} vs {_w(plan["transfer"])}），緩衝池會逐年變薄。')

    _render_backtest(principal_wan * 10000, shape, transfer_rate, preset)
    _render_comparison(principal_wan * 10000, shape, transfer_rate)

    st.markdown('### 想看細節的話')
    with st.expander('執行面：金額一年決定一次，動用分十二個月'):
        gain = monthly_execution_gain(plan['spend'])
        st.markdown(
            '**每年 1 月算一次**撥出額與今年的生活費總額，算完就固定，一整年不隨市場變動。'
            '**動用分十二個月**，還沒動用的部分留在緩衝池裡繼續生息：以 00865B 實測年化 2.89% 估，'
            f'比年初一次領出約多 **{_w(gain)}**／年（生活費的 {gain / plan["spend"]:.1%}）。'
            '上面的回測圖跑的就是分月動用。')
        st.warning('**分月動用不等於每月重算。** 每個月只取出年初總額的十二分之一；'
                   '若每個月都重算「緩衝池的 25%」，一年會領走緩衝池的 96.8%（1 − 0.75¹²）。'
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
