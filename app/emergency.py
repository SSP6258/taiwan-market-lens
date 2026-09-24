"""What the buffer-pool rule does NOT do: hand over a lump sum.

The rule pays a smooth income by construction -- a share of a pool that is itself
refilled by a share of another. Nothing in it produces a large one-off payment, and the
page that explains the rule never says so. This one does, and lays out the method: bridge
the emergency out of the buffer, then refill the buffer by whichever route is open.

A method page, not a calculator. The few figures it states are either the rule's own
arithmetic, derived from its rates so they cannot drift, or quotes carrying their source
and date. Nothing here fetches prices or takes input, so the page cannot fail to render.
"""
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


# The ways to refill the buffer, in the order they are worth trying. Held as data so the
# page and its tests read the same list, and so adding one is one edit.
#
# 理財型房貸 leads on one property none of the others have: its collateral is not marked
# to market, so a crash cannot withdraw it. 質押 borrows against the very thing that is
# falling when you need it. That ordering is the user's, taken 2026-09-23.
PLAYBOOK = [
    {'名稱': '理財型房貸', '關鍵': '⏰ 退休前必辦',
     '為什麼排這裡': '擔保品是房子，**不逐日按市價評價**，股市大跌不影響額度。'
                     '利率通常最低，沒動用幾乎不花錢。有額度就不必先墊，直接動用。',
     '代價': '**擔保品是你住的地方。** 額度多半定期審查，退休後可能被降或不續約。'},
    {'名稱': '質押借款', '關鍵': '看當時條件',
     '為什麼排這裡': '利率低於信貸，不賣持股、不改配置。',
     '代價': '**擔保品跟著市場跌**：大跌時可借額度縮水，還可能追繳。'},
    {'名稱': '信用貸款', '關鍵': '備而不用',
     '為什麼排這裡': '**不押任何東西**，沒有追繳。',
     '代價': '利率最高，多為**本息攤還**；退休後能否核貸待確認。'},
    {'名稱': '賣成長池換正2', '關鍵': '保留曝險',
     '為什麼排這裡': '賣一部分成長池，一半應急、一半買 00685L，曝險大致不變。',
     '代價': '**部位會自己長大，在市場高點最大。** 00685L 實測約 1.8 倍，曝險補不滿。'},
    {'名稱': '直接賣成長池', '關鍵': '永遠可用',
     '為什麼排這裡': '最簡單，不欠任何人。',
     '代價': '那筆錢不再複利，期末資產變少；生活費每年只少一點。'},
]

# Written out because "5 個錦囊" reads badly beside "四個". Derived rather than typed:
# the count drifted the first time an entry was added, and the heading said four while
# the table showed five.
_NUMERALS = {1: '一', 2: '兩', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八'}


def _numeral(n):
    return _NUMERALS.get(n, str(n))


def render_emergency():
    st.subheader('緊急支出：這條規則沒有準備的那件事')
    st.markdown(
        '**緩衝池退休法付的是平穩的生活費，不是一次性的大筆現金。** '
        '急用要另外安排：先墊，再補。')

    cost = income_cost_per_million()
    st.markdown('### 應急分兩步：先墊，再補')
    st.markdown(
        '**第一步：賣緩衝池（00865B）先墊。** 兩個營業日就能變現。'
        '緩衝池每月要付生活費，**至少留下辦好錦囊那幾個月的生活費**；不夠墊的部分直接走錦囊。\n\n'
        '**第二步：用錦囊把緩衝池補回去。** 時間壓力從兩天變成幾個月。')
    st.info(
        '**最好在下次重設生活費之前補回。** '
        f'重設時緩衝池每少 100 萬，當年生活費少 **{cost["buffer"] / 10000:.0f} 萬**；'
        f'同樣的錢從成長池拿，當年只少 {cost["growth"] / 10000:.0f} 萬。\n\n'
        '這是當年的差別，不是總代價：從緩衝池拿，衝擊集中在前幾年；'
        '從成長池拿，攤得很長，還少了那筆錢的複利。'
        '重設日期是自己訂的，來不及補可以往後延。')

    st.markdown(f'### 補回緩衝池的{_numeral(len(PLAYBOOK))}個錦囊，照這個順序試')
    st.markdown(
        '| | 做法 | | 好處 | 代價 |\n|---|---|---|---|---|\n' +
        '\n'.join(f'| **{i}** | **{p["名稱"]}** | {p["關鍵"]} | {p["為什麼排這裡"]} | {p["代價"]} |'
                  for i, p in enumerate(PLAYBOOK, 1)))
    st.error(
        '**房貸要在退休前辦。** 申辦看工作收入，退休後可能辦不下來。'
        '額度開著沒動用幾乎不花錢，放進退休前的待辦清單。')

    st.markdown('### 借錢時記得的幾件事')
    st.markdown(
        '- **押成長池，不押緩衝池。** 緩衝池每月要付生活費。\n'
        f'- **借款不超過被押部位的 {SAFE_LTV:.0%}。** '
        'LTV（貸款成數）＝ 借款 ÷ 擔保品市值，股價跌它就升；券商看的「維持率」是它的倒數。'
        f'跌 {SAFE_DROP:.0%} 後 LTV 約 {SAFE_LTV / (1 - SAFE_DROP):.0%}，'
        f'仍低於 {WARNING_LTV:.0%} 警戒線（專案研究的線，非券商規定）。\n'
        '- **利率門檻看「利息佔生活費幾成」**，不看絕對利率。\n'
        '- **質押利率逐檔不同：** '
        + '、'.join(f'{name} {rate:.1%}' for name, rate in OBSERVED_RATES)
        + f'（{OBSERVED_SOURCE}）。持有正2 後再質押會比較貴。')

    with st.expander('正2 那個做法：這段樣本裡是賺的，代價在別處'):
        st.markdown(
            f'實測（{MEASURED_WINDOW}）成長池 10% 換成 00685L：期末 **4.84 倍 → 6.23 倍**，'
            '最大回撤 −24.6% → −27.8%；正2 佔比由 11.1% 長到 32.9%，**那是它賺錢的結果**。\n\n'
            '但那次回撤發生在正2 只佔 14.1% 時，**大跌和大部位還沒同時出現過**。'
            '急用吃掉淨值後維持同樣曝險，等於槓桿變高。\n\n'
            '**房貸額度辦成了，這一項多半用不到。**')

    with st.expander('這一頁的數字從哪裡來'):
        st.markdown(
            '**規則算術**：100 萬對生活費的影響，由撥出率與領出率算出。\n\n'
            f'**實測**（退休8，{MEASURED_WINDOW}，還原價格）：正2 的報酬、回撤與佔比。'
            '歷史量測，不是預測；那段期間有台積電／AI 的超級循環。\n\n'
            f'**報價**：質押利率來自{OBSERVED_SOURCE}。\n\n'
            '**待自己確認**：理財型房貸的利率、審查週期與信用管制；'
            '信貸沒有薪資時能否用股票庫存當財力證明、有無循環型；質押後持股能否自由處分。\n\n'
            '未計稅費與交易成本。教育性資訊，不構成投資建議。')
