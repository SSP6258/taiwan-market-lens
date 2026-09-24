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
     '為什麼排這裡': '擔保品是房子，**不逐日按市價評價 —— 股市大跌不會抽走你的額度**。'
                     '利率通常最低、隨借隨還、沒動用幾乎不花錢，完全不碰這個組合。'
                     '有額度的話甚至不必先墊，直接動用。',
     '代價': '**擔保品是你住的地方。** 其他做法最慘是錢變少，這個最慘是沒地方住。'},
    {'名稱': '質押借款', '關鍵': '看當時條件',
     '為什麼排這裡': '利率低於信貸，不賣持股、不改結構、可逆。',
     '代價': '**擔保品跟著市場跌** —— 需要錢的時候正是利率被拉高、額度被收緊的時候，'
             '而且會追繳。**持股也會被設定。**'},
    {'名稱': '信用貸款', '關鍵': '不押任何東西',
     '為什麼排這裡': '**沒有追繳，持股也不會被設定**，組合一點都不受影響。',
     '代價': '利率最高，而且多半是**本息攤還** —— 每月固定要繳，'
             '跟「收入隨市場浮動」的形狀相反。'},
    {'名稱': '賣成長池換正2', '關鍵': '借不到才考慮',
     '為什麼排這裡': '**唯一不需要任何人點頭的一條。** '
                     '現在不持有正2，本身就是在保留這個轉換的選擇權。',
     '代價': '**部位會自己長大，而且在市場高點最大** —— 不是你決定的大小。'},
    {'名稱': '直接賣成長池', '關鍵': '永遠可用',
     '為什麼排這裡': '最簡單、零對手風險、不欠任何人。',
     '代價': '代價記在期末資產上，**對生活費幾乎無感**。'},
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
        '**緩衝池退休法解的是平滑的收入流，不是一次性的大筆現金。** '
        '生活費是緩衝池的一個比例，緩衝池一年只由成長池補一次 —— '
        '設計上沒有地方放得下「這個月要拿 300 萬」。')

    cost = income_cost_per_million()
    st.markdown('### 應急分兩步：先墊，再補')
    st.markdown(
        '**第一步：先賣緩衝池（00865B）應急。** 短債 ETF 兩個營業日就能變現，'
        '不必在急用的壓力下去辦借款。可以先墊多少：**緩衝池餘額扣掉今年剩下還要領的生活費**，'
        '否則今年的生活費會提早領光。\n\n'
        '**第二步：再用下面的錦囊把緩衝池補回去。** 時間壓力從兩天變成幾個月，'
        '每個錦囊都可以等條件好的時候再用。')
    st.info(
        '**最好在下一次重設生活費之前補回。** 規則每年重設一次生活費，'
        f'重設時緩衝池每少 100 萬，那一年的生活費就少 **{cost["buffer"] / 10000:.0f} 萬**'
        f'（同樣的錢從成長池拿，只少 {cost["growth"] / 10000:.0f} 萬）。\n\n'
        '來不及補回也不是災難：**重設日期是自己約定的，可以往後延**；'
        '就算照常重設，少領的錢也還留在緩衝池裡，只是晚一點領。')

    st.markdown(f'### 補回緩衝池的{_numeral(len(PLAYBOOK))}個錦囊，照這個順序試')
    st.markdown(
        '| | 做法 | | 為什麼排這裡 | 代價 |\n|---|---|---|---|---|\n' +
        '\n'.join(f'| **{i}** | **{p["名稱"]}** | {p["關鍵"]} | {p["為什麼排這裡"]} | {p["代價"]} |'
                  for i, p in enumerate(PLAYBOOK, 1)))
    st.error(
        '**第一個有死線，而且要在退休前辦。** 理財型房貸申辦時要看工作與收入，'
        f'**退休之後可能就辦不下來了** —— 其他{_numeral(len(PLAYBOOK) - 1)}個退休後都還能用，'
        '只有這個是資格性的。額度開著沒動用幾乎不花錢，'
        '把它放進退休前的待辦清單，跟勞保、健保怎麼轉放在一起。')

    st.markdown('### 借錢時記得的幾件事')
    st.markdown(
        '- **押成長池，不押緩衝池。** 緩衝池每個月要領生活費，設定成擔保品之後那個動作可能會卡住；'
        '成長池一年只在撥款時動一次。\n'
        f'- **借款控制在總資產的 {SAFE_LTV:.0%} 以內。** 就算股市跌 {SAFE_DROP:.0%}，'
        f'LTV 也只到 {SAFE_LTV / (1 - SAFE_DROP):.0%}，仍低於 {WARNING_LTV:.0%} 的警戒線'
        '（專案研究用的線，不是券商的斷頭規定）。\n'
        '- **利率門檻用「利息佔生活費的比例」來訂，不要用絕對利率。** '
        '同樣的利率，借得多或那年生活費低，負擔完全不同。\n'
        '- **質押利率逐檔不同：** '
        + '、'.join(f'{name} {rate:.1%}' for name, rate in OBSERVED_RATES)
        + f'（{OBSERVED_SOURCE}）。槓桿型較貴，走了正2 之後再質押，成本會變高。')

    with st.expander('正2 那個做法：它在這段樣本裡是賺的，代價在別的地方'):
        st.markdown(
            f'實測（{MEASURED_WINDOW}）把成長池裡 10% 換成 00685L：期末由 **4.84 倍變 6.23 倍**，'
            '最大回撤只由 −24.6% 深到 −27.8%。它佔成長池由 11.1% 長到 32.9%，'
            '**那是它贏了的結果，不是缺點**。\n\n'
            '但那個回撤是在正2 只佔 14.1% 時量到的，**大跌和大部位從來沒有同時發生過**；'
            '而且不再平衡的槓桿部位，佔比必然在市場高點最大。'
            '另外它維持的是曝險不是風險 —— 急用吃掉淨值後維持同樣曝險，等於把槓桿倍數推高。\n\n'
            '**如果房貸額度辦成了，這一項多半就不需要了。**')

    with st.expander('這一頁的數字從哪裡來'):
        st.markdown(
            '**規則的算術**：緩衝池與成長池各少 100 萬對生活費的影響，由撥出率與領出率推出來。\n\n'
            f'**實測**（退休8，{MEASURED_WINDOW}，還原價格）：正2 的報酬、回撤與佔比。'
            '那是一段歷史上的量測，不是預測 —— 那六年半是台股加上台積電／AI 的超級循環。\n\n'
            f'**報價**：質押利率來自{OBSERVED_SOURCE}，單一券商、單一時點。\n\n'
            '**這一頁問不到、你問得到的**：理財型房貸的利率與央行信用管制的影響；'
            '信用貸款在沒有薪資時能不能用股票庫存當財力證明、有沒有循環動用型；'
            '質押設定後的持股還能不能自由處分。\n\n'
            '全部未計稅、費用與交易成本。此頁為教育性資訊，不構成投資建議。')
