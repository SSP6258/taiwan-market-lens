"""What the buffer-pool rule does NOT do: hand over a lump sum.

The rule pays a smooth income by construction -- a share of a pool that is itself
refilled by a share of another. Nothing in it produces a large one-off payment, and the
page that explains the rule never says so. This one does, and then lays out what the
three ways of raising that money actually cost, in the currency each one charges.

Nothing here fetches prices. Every live figure on the page is arithmetic over the rule's
own rates and the principal typed in, so the page opens instantly and has no failure
path. The measured figures it quotes are marked as measurements, with their window.
"""
import pandas as pd
import streamlit as st

from retirement_strategy import (PRESET, TRANSFER_RATE, TRANSFER_RANGE, WITHDRAW_RATE,
                                 growth_share, pool_plan)
from ui import wan

# Where the measured passages come from. Named once so the page cannot quote a window it
# did not measure, and so a later re-run has one place to update.
MEASURED_WINDOW = '2020/01 — 2026/09'
MEASURED_PRESET = '退休8（0050 50% ＋ 00662 40% ＋ 00865B 10%）'

# The drawdowns the LTV table is stressed against. 60% is far past anything in the sample
# -- 退休8's worst month-end drawdown over the measured window was -22.3% -- which is the
# point: a threshold that only survives what has already happened is not a threshold.
STRESS_DROPS = (0.25, 0.40, 0.50, 0.60)
STARTING_LTVS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
# The line the project's own 40-year study drew, not a broker's maintenance requirement.
WARNING_LTV = 0.50


def income_cost_per_million(transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """What one million taken out of each pool costs in future annual income.

    The whole page turns on the ratio between these two, so they are derived from the
    rates rather than written down: the growth pool only reaches the wallet through a
    transfer and then a withdrawal, the buffer is already one step from it.
    """
    return {'growth': 1_000_000 * transfer_rate * withdraw_rate,
            'buffer': 1_000_000 * withdraw_rate}


def ltv_after(starting_ltv, drop):
    """The loan is fixed; only the collateral falls."""
    return starting_ltv / (1 - drop)


def ltv_table(principal, drops=STRESS_DROPS, starts=STARTING_LTVS):
    """Starting LTVs against the drawdowns that would follow them, with what each borrows."""
    rows = []
    for start in starts:
        row = {'起始 LTV': start, '可借金額': principal * start}
        for drop in drops:
            row[f'跌 {drop:.0%} 後'] = ltv_after(start, drop)
        # 0.0 rather than None: the column goes into a DataFrame, which turns None into
        # NaN, and NaN is truthy -- the formatter would print "跌 nan%" for the row that
        # survives nothing. Zero reads as "not even the shallowest drop" and stays a float.
        held = [d for d in drops if ltv_after(start, d) < WARNING_LTV]
        row['撐得住的最深跌幅'] = max(held) if held else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def interest_share(loan, rate, annual_spend):
    """Interest as a share of one year's living expenses.

    Expressed against income rather than as a bare rate because that is the number that
    scales: the same 3% is a different burden on a larger loan or a leaner year, and a
    threshold written as a rate cannot see either.
    """
    if not annual_spend:
        return float('nan')
    return loan * rate / annual_spend


# The four ways to raise the money, in the order they are worth trying. Held as data so
# the page and its tests read the same list, and so adding a fifth is one edit.
#
# 理財型房貸 leads on one property none of the others have: its collateral is not marked
# to market, so a crash cannot withdraw it. 質押 borrows against the very thing that is
# falling when you need it. That ordering is the user's, taken 2026-09-23.
PLAYBOOK = [
    {'名稱': '理財型房貸', '關鍵': '⏰ 退休前必辦',
     '為什麼排這裡': '擔保品是房子，**不逐日按市價評價 —— 股市大跌不會抽走你的額度**。'
                     '利率通常也最低，隨借隨還、沒動用幾乎不花錢，而且完全不碰這個組合。',
     '代價': '**擔保品是你住的地方。** 其餘三個最慘是錢變少，這個最慘是沒地方住。'},
    {'名稱': '質押借款', '關鍵': '看當時條件',
     '為什麼排這裡': '不動持股、不改結構、可逆。額度先開好，用不用另說。',
     '代價': '**擔保品跟著市場跌** —— 需要錢的時候正是利率被拉高、額度被收緊的時候，'
             '而且會追繳。'},
    {'名稱': '賣成長池換正2', '關鍵': '借不到才考慮',
     '為什麼排這裡': '不依賴任何人，維持得住原本的曝險金額。'
                     '在這段樣本裡它是賺的 —— 成長池期末 4.84 倍 → 6.23 倍。',
     '代價': '**部位會自己長大，而且在市場高點最大** —— 不是你決定的大小。'
             '而且是在市場壓力下買進槓桿。'},
    {'名稱': '直接賣成長池', '關鍵': '永遠可用',
     '為什麼排這裡': '最簡單、零對手風險、不欠任何人。',
     '代價': '代價全記在期末資產上，**但對生活費幾乎無感**。'},
]


def render_emergency():
    st.subheader('緊急支出：這條規則沒有準備的那件事')
    st.markdown(
        '**緩衝池退休法解的是平滑的收入流，不是一次性的大筆現金。** '
        '生活費是緩衝池的一個比例，緩衝池一年只由成長池補一次 —— '
        '設計上沒有地方放得下「這個月要拿 300 萬」。')

    st.markdown('### 四個錦囊，照這個順序試')
    st.markdown(
        '| | 做法 | | 為什麼排這裡 | 代價 |\n|---|---|---|---|---|\n' +
        '\n'.join(f'| **{i}** | **{p["名稱"]}** | {p["關鍵"]} | {p["為什麼排這裡"]} | {p["代價"]} |'
                  for i, p in enumerate(PLAYBOOK, 1)))
    st.error(
        '**最優先、而且有死線的是第一個。** 理財型房貸申辦時要看工作與收入，'
        '**退休那天起可能就辦不下來了** —— 其他三個退休後都還能用，只有這個是資格性的，'
        '而資格建立在你即將失去的那樣東西上。\n\n'
        '**需求在退休後，資格在退休前。** 把它放進退休前的截止清單，'
        '跟勞保、健保怎麼轉放在一起。額度開著沒動用幾乎不花錢。')

    st.markdown('### 真的要動這個組合的話，別動錯池子')
    left, right = st.columns([1.2, 1.8])
    principal_wan = left.number_input(
        '本金（萬元）', min_value=100.0, max_value=100000.0, step=100.0,
        value=3000.0, key='emergency_principal_wan')
    transfer_rate = right.slider(
        '每年從成長池撥出（%）', min_value=TRANSFER_RANGE[0], max_value=TRANSFER_RANGE[1],
        value=TRANSFER_RATE * 100, step=0.5, format='%.1f%%', key='emergency_transfer_rate') / 100
    principal = principal_wan * 10000
    plan = pool_plan(principal, growth_share(PRESET), transfer_rate)
    cost = income_cost_per_million(transfer_rate)

    cards = st.columns(2)
    cards[0].metric('從成長池拿 100 萬', f'往後每年生活費少 {wan(cost["growth"]) or "不到 1 萬"}',
                    delta='影響小，代價記在期末資產',
                    delta_color='off', delta_arrow='off', border=True)
    cards[1].metric('從緩衝池拿 100 萬', f'隔年生活費少 {wan(cost["buffer"])}',
                    delta='生活費立刻被砍，要好幾年才長回來',
                    delta_color='off', delta_arrow='off', border=True)
    st.warning(
        '**緩衝池看起來最像緊急預備金，實際上最不該動 —— 它是收入引擎，不是水庫。** '
        f'差 {WITHDRAW_RATE / (transfer_rate * WITHDRAW_RATE):.0f} 倍，而這是規則的算術，'
        '不依賴任何報酬假設。')
    st.caption(f'目前設定：緩衝池 {wan(plan["buffer"])}、成長池 {wan(plan["growth"])}、'
               f'首年生活費約 {wan(plan["spend"])}。')

    with st.expander('借錢之前先訂門檻：LTV 與利率'):
        st.markdown('**條件式的計畫要事先寫下條件。**「利率不會太高」在平靜時是一個數字，'
                    '在家人躺病床、市場又在跌的時候會變成另一個數字。')
        table = ltv_table(principal)
        show = pd.DataFrame({
            '起始 LTV': table['起始 LTV'].map('{:.0%}'.format),
            '可借金額': table['可借金額'].map(lambda v: wan(v) or f'{v:,.0f} 元'),
            **{f'跌 {d:.0%} 後': table[f'跌 {d:.0%} 後'].map('{:.0%}'.format) for d in STRESS_DROPS},
            '撐得住的最深跌幅': table['撐得住的最深跌幅'].map(
                lambda d: f'跌 {d:.0%} 仍低於 {WARNING_LTV:.0%}' if d > 0 else '—'),
        })
        st.dataframe(show, hide_index=True, width='stretch')
        st.caption(
            f'擔保品縮水、債務不動，所以跌得越深 LTV 越高。{WARNING_LTV:.0%} 是專案那份 40 年研究'
            '用的警戒線，**不是券商的實際斷頭規定**。'
            '那份研究裡 21–30% 的路徑會摸到警戒線 —— **那是每年生活費全靠借**，不是一次借一筆。')
        loan_wan = st.number_input('打算借多少（萬元）', min_value=10.0, max_value=principal_wan,
                                   step=50.0, value=min(300.0, principal_wan),
                                   key='emergency_loan_wan')
        rates = [0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
        st.dataframe(pd.DataFrame({
            '年利率': [f'{r:.0%}' for r in rates],
            '一年利息': [wan(loan_wan * 10000 * r) or f'{loan_wan * 10000 * r:,.0f} 元' for r in rates],
            '佔首年生活費': [f'{interest_share(loan_wan * 10000, r, plan["spend"]):.0%}' for r in rates],
        }), hide_index=True, width='stretch')
        st.caption('**門檻建議寫成「佔生活費的比例」而不是絕對利率** —— 只有前者會隨借款金額與'
                   '收入縮放。而且利息是確定的，你避開的損失是不確定的，所以要訂得比打平更保守。')

    with st.expander('正2 那個做法：它在這段樣本裡是賺的，代價在別的地方'):
        st.markdown(
            f'**先說它好的地方，因為它確實好。** 實測（{MEASURED_WINDOW}）把成長池裡 10% '
            '換成 00685L：期末由 **4.84 倍變 6.23 倍**，而最大回撤只由 −24.6% 深到 −27.8%。'
            '它佔成長池的比例由 11.1% 長到 32.9%，**那是它贏了的結果，不是缺點**。\n\n'
            '**但那個回撤數字低估了現在的風險。** −27.8% 發生在 2022-10，'
            '當時正2 只佔成長池 **14.1%** —— **大跌和大部位從來沒有同時發生過**。'
            '把今天 32.9% 的權重套回 2022 那段跌勢，會是 **−31.1%** 而不是 −26.2%。\n\n'
            '**而且它的佔比在市場高點最大。** 佔比最高的三個月（33.6%／33.0%／32.9%），'
            '成長池都正好在歷史新高上。規則從不平衡成長池內部，'
            '所以**槓桿曝險必然在市場跑最多的時候最大**。以 1.81 倍計，'
            '33% 的部位帶來的實質台股曝險是成長池的 **60%** —— 那不是你當初決定的部位大小。\n\n'
            '**它維持的是曝險，不是風險。** 急用吃掉一部分淨值之後維持同樣的絕對曝險，'
            '等於把槓桿倍數推高。剛受到財富衝擊就提高相對風險，方向是反的。\n\n'
            '順帶：00685L 的日報酬迴歸斜率實測 **1.81 倍不是 2 倍**，'
            '所以「賣 100 萬買 50 萬」拿到的約是 90 萬曝險。\n\n'
            '**如果房貸額度辦成了，這一項多半就不需要了** —— '
            '它存在的理由是「借不到錢時的自救」。')

    with st.expander('這一頁的數字從哪裡來，以及不要拿它當什麼用'):
        st.markdown(
            '**現算的**：兩個池子的生活費代價、LTV 表、利息佔比 —— 由本金與費率推出來，'
            '改了就跟著變。這一頁不讀行情，所以永遠秒開、沒有失敗路徑。\n\n'
            f'**實測的**（{MEASURED_PRESET}，{MEASURED_WINDOW}，還原價格）：'
            '正2 在成長池裡的漂移、1.81 倍斜率。'
            '**那是一段歷史上的量測，不是預測** —— 而且那六年半是台股加上台積電／AI 的超級循環，'
            '槓桿在趨勢市場佔便宜、震盪市場吃虧，這個樣本幾乎沒有橫盤段。\n\n'
            '**無法驗證的**：台灣券商當前的質押條件、理財型房貸的利率與央行信用管制的影響。'
            '這些會實質改變上面的排序，而那是你手上才有的當期資訊。\n\n'
            '**還有兩件事要自己看清楚**：理財型房貸的動用期限、續約與重新鑑價條款 —— '
            '「額度開著」跟「額度永遠在」是兩回事；'
            '以及循環額度不追繳、隨借隨還會讓借錢變得太容易，'
            '而退休後沒有勞動收入可以還款，**建議連「什麼情況才動用」也一起先寫下來**。\n\n'
            '全部未計稅、費用與交易成本。此頁為教育性資訊，不構成投資建議。')
