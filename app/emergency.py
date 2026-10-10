"""What the buffer-pool rule does NOT do: hand over a lump sum.

The rule pays a smooth income by construction -- a share of a pool that is itself
refilled by a share of another. Nothing in it produces a large one-off payment, and the
page that explains the rule never says so. This one does, and lays out the method: bridge
the emergency out of the buffer, then refill it -- by borrowing only when the money is
coming back, and by selling the growth pool when it is not.

A method page, not a calculator. The few figures it states are either the rule's own
arithmetic, derived from its rates so they cannot drift, or quotes carrying their source
and date. Nothing here fetches prices or takes input, so the page cannot fail to render.
"""
import re

import streamlit as st

from retirement_strategy import TRANSFER_RATE, WITHDRAW_RATE

# Where the measured passages come from. Named once so the page cannot quote a window it
# did not measure, and so a later re-run has one place to update.
MEASURED_WINDOW = '2020/01 — 2026/09'

# The line the project's own 40-year study drew, not a broker's maintenance requirement.
WARNING_LTV = 0.50
# Borrow no more than this share of the portfolio, and a fall of SAFE_DROP -- far past
# 退休8's worst month-end drawdown of -22.3% over the measured window -- still leaves the
# loan under the warning line. Stated as a rule of thumb; the test checks the arithmetic.
SAFE_LTV = 0.15
SAFE_DROP = 0.60

# Quoted rates, not an assumption: one broker's collateral calculator, seen by the user
# on 2026-09-24. The project's 40-year study assumed 3%, which turns out to be below
# anything actually on offer. Rates are per instrument, which the study did not model --
# a leveraged holding costs half again as much to borrow against as a plain index one.
OBSERVED_RATES = [('一般股票型 ETF', 0.04), ('債券型 ETF', 0.045),
                  ('槓桿型與期貨型', 0.06)]
OBSERVED_SOURCE = '永豐金證券擔保品試算，2026-09-24'


def income_cost_per_million(transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """What one million missing from each pool costs in a year's income at the reset.

    The reason the buffer has to be refilled, so it is derived from the rates rather than
    written down: the growth pool only reaches the wallet through a transfer and then a
    withdrawal, the buffer is already one step from it.
    """
    return {'growth': 1_000_000 * transfer_rate * withdraw_rate,
            'buffer': 1_000_000 * withdraw_rate}


# The ways to refill the buffer, split by the one question that decides between them: is
# the money coming back? Held as data so the page and its tests read the same lists.
#
# Borrowing is a bridge, not a source. After retirement there is no pay to repay it from,
# so a loan against money that is not coming back ends up repaid by selling the growth
# pool anyway -- the same sale, later, with interest on top and leverage carried through
# the months right after a shock. So borrowing is offered only when a repayment is on its
# way, and selling is the default when it is not. The user's call, 2026-10-10; before
# that the two were one list with selling last.
#
# Within the bridge, 理財型房貸 leads on one property none of the others have: its
# collateral is not marked to market, so a crash cannot withdraw it. 質押 borrows against
# the very thing that is falling. 信貸 comes last: its only advantage, no margin call, is
# one selling also has, and it is the dearest and amortises out of the monthly income.
BRIDGE = [
    {'名稱': '理財型房貸', '關鍵': '⏰ 退休前必辦',
     '為什麼排這裡': '擔保品是房子，**不逐日按市價評價**，股市大跌不影響額度。'
                     '利率通常最低，沒動用幾乎不花錢。有額度就不必先墊，直接動用。',
     '代價': '**擔保品是你住的地方。** 額度多半定期審查，退休後可能被降或不續約。'},
    {'名稱': '質押借款', '關鍵': '看當時條件',
     '為什麼排這裡': '利率低於信貸，不賣持股、不改配置。',
     '代價': '**擔保品跟著市場跌**：大跌時可借額度縮水，還可能追繳。'},
    {'名稱': '信用貸款', '關鍵': '備而不用',
     '為什麼排這裡': '**不押任何東西**，沒有追繳。',
     '代價': '利率最高，多為**本息攤還**，每月從生活費付；退休後能否核貸待確認。'},
]

# Selling first because it owes nobody. 正2 is not a separate route but a way of doing the
# same sale, so it follows as the variant rather than ranking as its own option.
PERMANENT = [
    {'名稱': '直接賣成長池', '關鍵': '預設做法',
     '為什麼排這裡': '不欠任何人、沒有利息。國內股票型 ETF 只有 0.1% 證交稅，不課證所稅。',
     '代價': '那筆錢不再複利，期末資產變少；生活費當年只少一點，之後隨成長池變小慢慢少。'},
    {'名稱': '賣成長池，一半換正2', '關鍵': '進階：保留曝險',
     '為什麼排這裡': '賣一部分成長池，一半應急、一半買 00685L，曝險大致不變。',
     '代價': '**剛受衝擊就提高槓桿，部位在市場高點最大。** 00685L 實測約 1.8 倍，曝險補不滿；'
             '再拿它質押，利率較高。'},
]

# Written out because "3 個錦囊" reads badly beside "兩步". Derived rather than typed:
# the count drifted the first time an entry was added, and the heading said four while
# the table showed five.
_NUMERALS = {1: '一', 2: '兩', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八'}


def _numeral(n):
    return _NUMERALS.get(n, str(n))


# The page's own cards, in the visual language of the 緩衝池退休法 diagram: a coloured top
# rule says which pool or which path a card belongs to, and nothing else is coloured.
# Neutral lines and fills are translucent grey so the same CSS reads in light and dark.
_CSS = """<style>
.em{--buf:#D2963F;--grow:#3E9C86;--loan:#4F7FB5;--flat:#7F9BBA;--cost:#C8604E;
  --ln:rgba(128,128,128,.28);--soft:rgba(128,128,128,.08);font-size:14px;line-height:1.65;margin:2px 0 6px}
.em .flow{display:grid;grid-template-columns:1fr auto 1fr;align-items:stretch}
.em .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.em .grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.em .card{border:1px solid var(--ln);border-radius:12px;padding:14px 16px;display:grid;gap:6px;align-content:start}
.em .buf{border-top:4px solid var(--buf)} .em .grow{border-top:4px solid var(--grow)}
.em .loan{border-top:4px solid var(--loan)} .em .flat{border-top:4px solid var(--flat)}
.em .k{font-size:12px;letter-spacing:.06em;opacity:.65}
.em .t{font-weight:700;font-size:17px}
.em .buf .t{color:var(--buf)} .em .grow .t{color:var(--grow)} .em .loan .t{color:var(--loan)} .em .flat .t{color:var(--flat)}
.em .p{margin:0;font-size:13.5px}
.em .eg{margin:0;font-size:12.5px;opacity:.7}
.em .route{background:var(--soft);border-radius:8px;padding:6px 10px;font-size:13.5px;font-weight:600}
.em .arr{display:grid;justify-items:center;align-content:center;gap:2px;padding:0 12px;min-width:110px;text-align:center}
.em .arr .v{font-size:12.5px;opacity:.7}
.em .arr .line{width:100%;height:0;border-top:1.6px solid currentColor;position:relative;margin:4px 0;opacity:.6}
.em .arr .line::after{content:"";position:absolute;right:-2px;top:-6px;border:5.5px solid transparent;border-left:9px solid currentColor;border-right:0}
.em .opt{border:1px solid var(--ln);border-radius:12px;padding:12px 16px;display:grid;
  grid-template-columns:34px 1fr;column-gap:12px;row-gap:8px;margin-bottom:10px}
.em .opt .n{grid-row:span 2;width:30px;height:30px;border-radius:99px;display:grid;place-items:center;
  font-weight:700;color:#fff;font-size:14px}
.em .opt.loan .n{background:var(--loan)} .em .opt.grow .n{background:var(--grow)}
.em .head{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.em .head b{font-size:16px}
.em .tag{font-size:11.5px;font-weight:700;padding:1px 9px;border-radius:99px;background:var(--soft);border:1px solid var(--ln)}
.em .tag.hot{background:var(--cost);border-color:var(--cost);color:#fff}
.em .tag.def{background:var(--grow);border-color:var(--grow);color:#fff}
.em .pc{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.em .pro,.em .con{font-size:13.5px;margin:0;padding:6px 10px;border-radius:8px;background:var(--soft)}
.em .pro{border-left:3px solid var(--grow)} .em .con{border-left:3px solid var(--cost)}
.em .pro i,.em .con i{display:block;font-style:normal;font-size:11.5px;opacity:.65;letter-spacing:.06em}
@media (max-width:760px){
  .em .flow,.em .grid3,.em .grid2,.em .pc{grid-template-columns:1fr}
  .em .arr{padding:8px 0}
  .em .arr .line{width:0;height:24px;border-top:0;border-left:1.6px solid currentColor}
  .em .arr .line::after{right:auto;left:-6px;top:auto;bottom:-2px;border:5.5px solid transparent;border-top:9px solid currentColor;border-bottom:0}
}
</style>"""


def _bold(text):
    """The playbook is written in Markdown's **bold**; the cards are HTML."""
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)


def _html(body):
    st.html(_CSS + f'<div class="em">{body}</div>')


def _playbook_cards(entries, kind):
    """One card per option: rank, name and tag on top, what it buys beside what it costs."""
    def tag(text):
        hot = 'hot' if '必辦' in text else 'def' if '預設' in text else ''
        return f'<span class="tag {hot}">{text}</span>'
    return ''.join(
        f'<div class="opt {kind}"><div class="n">{i}</div>'
        f'<div class="head"><b>{p["名稱"]}</b>{tag(p["關鍵"])}</div>'
        f'<div class="pc"><p class="pro"><i>好處</i>{_bold(p["為什麼排這裡"])}</p>'
        f'<p class="con"><i>代價</i>{_bold(p["代價"])}</p></div></div>'
        for i, p in enumerate(entries, 1))


def render_emergency():
    st.subheader('緊急支出：這條規則沒有準備的那件事')
    st.markdown(
        '**緩衝池退休法付的是平穩的生活費，不是一次性的大筆現金。** '
        '急用要另外安排：先墊，再補。')

    cost = income_cost_per_million()
    st.markdown('### 應急分兩步：先墊，再補')
    _html('<div class="flow">'
          '<div class="card buf"><div class="k">第一步</div><div class="t">賣緩衝池先墊</div>'
          '<p class="p">00865B 兩個營業日就能變現。</p>'
          '<p class="eg">緩衝池每月要付生活費：至少留下辦好錦囊那幾個月的生活費，不夠墊的部分直接走錦囊。</p></div>'
          '<div class="arr"><div class="v">兩天內拿到錢</div><div class="line"></div>'
          '<div class="v">幾個月內補回</div></div>'
          '<div class="card grow"><div class="k">第二步</div><div class="t">用錦囊補回緩衝池</div>'
          '<p class="p">時間壓力從兩天變成幾個月。</p>'
          '<p class="eg">走哪一條，看下面「這筆錢會不會回來」。</p></div>'
          '</div>')
    st.info(
        '**最好在下次重設生活費之前補回。** '
        f'重設時緩衝池每少 100 萬，當年生活費少 **{cost["buffer"] / 10000:.0f} 萬**；'
        f'同樣的錢從成長池拿，當年只少 {cost["growth"] / 10000:.0f} 萬。\n\n'
        '這是當年的差別，不是總代價：從緩衝池拿，衝擊集中在前幾年；'
        '從成長池拿，攤得很長，還少了那筆錢的複利。'
        '重設日期是自己訂的，來不及補可以往後延。')

    st.markdown('### 補回之前先問：這筆錢之後會回來嗎？')
    _html('<div class="grid3">'
          '<div class="card loan"><div class="k">之後會回來</div><div class="t">借錢過渡</div>'
          '<p class="eg">保險理賠、賣房款、定存到期</p>'
          '<div class="route">理財型房貸 → 質押 → 信貸</div>'
          '<p class="eg">錢回來就還清。</p></div>'
          '<div class="card grow"><div class="k">不會回來</div><div class="t">直接賣成長池</div>'
          '<p class="eg">醫療自付、房屋修繕、資助家人</p>'
          '<div class="route">直接賣 → 進階：一半換正2</div>'
          '<p class="eg">不欠任何人，沒有利息。</p></div>'
          '<div class="card flat"><div class="k">每年都要付</div><div class="t">這不是急用</div>'
          '<p class="eg">長照、看護</p>'
          '<div class="route">回頭檢視生活費水準</div>'
          '<p class="eg">不要靠借款撐。</p></div>'
          '</div>')
    st.caption('退休後沒有薪水可以還款。借來補一筆不會回來的錢，最後還是要賣成長池還 —— '
               '等於延後賣、多付利息，還在剛受衝擊時加了槓桿。')

    st.markdown(f'### 會回來：借錢過渡的{_numeral(len(BRIDGE))}個錦囊，照這個順序試')
    _html(_playbook_cards(BRIDGE, 'loan'))
    st.error(
        '**房貸要在退休前辦。** 申辦看工作收入，退休後可能辦不下來。'
        '額度開著沒動用幾乎不花錢，放進退休前的待辦清單。')

    st.markdown('### 借錢時記得的幾件事')
    _html('<div class="grid2">'
          '<div class="card"><div class="t">押成長池，不押緩衝池</div>'
          '<p class="p">緩衝池每月要付生活費。</p></div>'
          f'<div class="card"><div class="t">借款 ≤ 被押部位的 {SAFE_LTV:.0%}</div>'
          f'<p class="p">跌 {SAFE_DROP:.0%} 後 LTV 約 {SAFE_LTV / (1 - SAFE_DROP):.0%}，'
          f'仍低於 {WARNING_LTV:.0%} 警戒線。</p>'
          '<p class="eg">LTV（貸款成數）＝ 借款 ÷ 擔保品市值，股價跌它就升；券商看的「維持率」是它的倒數。'
          '警戒線是專案研究的線，非券商規定。</p></div>'
          '<div class="card"><div class="t">利率門檻看「利息佔生活費幾成」</div>'
          '<p class="p">不看絕對利率。</p></div>'
          '<div class="card"><div class="t">質押利率逐檔不同</div>'
          '<p class="p">' + '、'.join(f'{name} <b>{rate:.1%}</b>' for name, rate in OBSERVED_RATES)
          + '</p>'
          f'<p class="eg">{OBSERVED_SOURCE}。持有正2 後再質押會比較貴。</p></div>'
          '</div>')

    st.markdown('### 不會回來：賣成長池，照這個順序試')
    _html(_playbook_cards(PERMANENT, 'grow'))

    with st.expander('正2 那個做法：這段樣本裡是賺的，代價在別處'):
        st.markdown(
            f'實測（{MEASURED_WINDOW}）成長池 10% 換成 00685L：期末 **4.84 倍 → 6.23 倍**，'
            '最大回撤 −24.6% → −27.8%；正2 佔比由 11.1% 長到 32.9%，**那是它賺錢的結果**。\n\n'
            '但那次回撤發生在正2 只佔 14.1% 時，**大跌和大部位還沒同時出現過**。'
            '急用吃掉淨值後維持同樣曝險，等於槓桿變高。\n\n'
            '**只有錢不會回來時才走到這一步，而且直接賣通常就夠了。**')

    with st.expander('這一頁的數字從哪裡來'):
        st.markdown(
            '**規則算術**：100 萬對生活費的影響，由撥出率與領出率算出。\n\n'
            f'**實測**（退休8，{MEASURED_WINDOW}，還原價格）：正2 的報酬、回撤與佔比。'
            '歷史量測，不是預測；那段期間有台積電／AI 的超級循環。\n\n'
            f'**報價**：質押利率來自{OBSERVED_SOURCE}。\n\n'
            '**待自己確認**：理財型房貸的利率、審查週期與信用管制；'
            '信貸沒有薪資時能否用股票庫存當財力證明、有無循環型；質押後持股能否自由處分。\n\n'
            '未計稅費與交易成本。教育性資訊，不構成投資建議。')
