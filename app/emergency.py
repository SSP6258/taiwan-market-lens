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


def _section(title, body):
    st.markdown(f'### {title}')
    st.markdown(body)


def render_emergency():
    st.subheader('緊急支出：這條規則沒有準備的那件事')
    st.markdown(
        '**緩衝池退休法解的是平滑的收入流，不是一次性的大筆現金。** '
        '生活費是緩衝池的一個比例，而緩衝池一年只由成長池補一次 —— '
        '設計上沒有任何地方放得下「這個月要拿 300 萬」。\n\n'
        '小孩留學那種**可預期**的大額支出不屬於這裡：你會提前五到十年知道，'
        '它該有自己的準備路徑。這一頁講的是**時間與金額都不可預測**的那種。')

    left, right = st.columns([1.2, 1.8])
    principal_wan = left.number_input(
        '本金（萬元）', min_value=100.0, max_value=100000.0, step=100.0,
        value=3000.0, key='emergency_principal_wan')
    transfer_rate = right.slider(
        '每年從成長池撥出（%）', min_value=TRANSFER_RANGE[0], max_value=TRANSFER_RANGE[1],
        value=TRANSFER_RATE * 100, step=0.5, format='%.1f%%', key='emergency_transfer_rate',
        help='跟「緩衝池退休法」分頁是同一個數字，兩頁各自調整、互不影響。') / 100
    principal = principal_wan * 10000
    plan = pool_plan(principal, growth_share(PRESET), transfer_rate)

    _section(
        '從哪個池子拿，差 %.0f 倍' % (WITHDRAW_RATE / (transfer_rate * WITHDRAW_RATE)),
        '這是全頁唯一**不依賴任何報酬假設**的結論，所以放在最前面。')
    cost = income_cost_per_million(transfer_rate)
    cards = st.columns(2)
    cards[0].metric('從成長池拿 100 萬', f'往後每年生活費少 {wan(cost["growth"]) or "不到 1 萬"}',
                    delta=f'100 萬 × 撥出率 {transfer_rate:.1%} × 領出率 {WITHDRAW_RATE:.0%}',
                    delta_color='off', delta_arrow='off', border=True)
    cards[1].metric('從緩衝池拿 100 萬', f'隔年生活費少 {wan(cost["buffer"])}',
                    delta=f'100 萬 × 領出率 {WITHDRAW_RATE:.0%}',
                    delta_color='off', delta_arrow='off', border=True)
    st.warning(
        '**緩衝池看起來最像緊急預備金，實際上最不該動。** '
        '它是收入引擎，不是水庫 —— 動它，你往後每年的生活費立刻被砍，而且要好幾年才長得回來。'
        f'（實測：{MEASURED_PRESET} 在 {MEASURED_WINDOW} 於 2023-03 抽走 300 萬，'
        '隔年生活費由 145 萬掉到 66 萬，再隔年也只回到 111 萬，同期不抽是 179 萬。）')
    st.caption(f'目前設定下首年生活費約 {wan(plan["spend"])}，'
               f'緩衝池 {wan(plan["buffer"])}、成長池 {wan(plan["growth"])}。')

    _section('三種做法，差別不在誰比較好，在失敗的方式不一樣',
             '沒有一欄是推薦。每一種都在某個情境下是對的，代價付在不同的地方。')
    st.markdown(
        '| | 質押借款 | 賣成長池換正2 | 直接賣成長池 |\n'
        '|---|---|---|---|\n'
        '| 交易對手風險 | **有**：利率與額度可能收緊，而且往往在你最需要時 | 無 | 無 |\n'
        '| 追繳風險 | **有** | 無，最慘是那筆錢歸零 | 無 |\n'
        '| 對配置結構 | 不改變，每年撥款照舊 | **破壞免再平衡的性質**（見下） | 不改變 |\n'
        '| 可逆 | 還掉就回到原狀 | 單向門，換回來要再付一次成本 | 否 |\n'
        f'| 對生活費 | 無影響 | 無影響 | 每 100 萬少 {wan(cost["growth"]) or "不到 1 萬"} |\n'
        '| 持續現金流出 | **利息** | 無 | 無 |\n')
    st.markdown(
        '**「賣掉部分持股、拿一半應急、另一半買正2 維持曝險」這個做法要特別講兩件事。**\n\n'
        f'一、**它會腐蝕這條規則最值錢的性質。** 實測（{MEASURED_WINDOW}）把成長池裡 10% '
        '換成 00685L，六年半後它佔成長池由 11.1% 漲到 **33.0%**，成長池最大回撤由 '
        '−24.6% 深到 −27.8%。規則從不平衡成長池內部，所以那個比例只會一路漂 —— '
        '而「免再平衡」正是這條規則宣稱的三個結構性優勢之一。\n\n'
        '二、**它維持的是曝險，不是風險。** 急用吃掉一部分淨值之後，維持同樣的絕對曝險'
        '等於把槓桿倍數推高。剛受到財富衝擊就提高相對風險，方向是反的 —— '
        '這可以是一個清醒的決定，但它不該是「維持曝險」這句話的副產品。\n\n'
        '順帶：00685L 的日報酬迴歸斜率實測 **1.81 倍不是 2 倍**，'
        '所以「賣 100 萬買 50 萬」拿到的約是 90 萬曝險。')

    _section('如果要質押，先把門檻訂死：LTV',
             '條件式的計畫需要事先寫下條件。「利率不會太高」在平靜時是一個數字，'
             '在家人躺病床、市場又在跌的時候會變成另一個數字。')
    table = ltv_table(principal)
    show = table.copy()
    show['起始 LTV'] = show['起始 LTV'].map('{:.0%}'.format)
    show['可借金額'] = show['可借金額'].map(lambda v: wan(v) or f'{v:,.0f} 元')
    for drop in STRESS_DROPS:
        show[f'跌 {drop:.0%} 後'] = show[f'跌 {drop:.0%} 後'].map('{:.0%}'.format)
    show['撐得住的最深跌幅'] = table['撐得住的最深跌幅'].map(
        lambda d: f'跌 {d:.0%} 仍低於 {WARNING_LTV:.0%}' if d > 0 else '—')
    st.dataframe(show, hide_index=True, width='stretch')
    st.caption(
        f'擔保品縮水、債務不動，所以跌幅越深 LTV 越高。{WARNING_LTV:.0%} 是專案那份 40 年研究'
        '用的警戒線，**不是券商的實際斷頭規定** —— 實際的維持率、折算率、哪些標的不收，'
        '各家不同，要自己確認。'
        f'參考：{MEASURED_PRESET} 在 {MEASURED_WINDOW} 的最大月底回撤是 −22.3%，'
        '表上的 −50%、−60% 已經遠超過樣本裡發生過的事。')
    st.info(
        '那份研究裡緩衝池法有 21–30% 的路徑會摸到警戒線 —— **那是「每年生活費全靠借」**，'
        '不是一次借一筆。在低 LTV 借一次，追繳風險小得多。')

    _section('利率門檻建議用「佔生活費的比例」，不要用絕對數字',
             '同樣的利率，借得多或那年生活費低，負擔完全不同。'
             '寫成絕對利率的門檻看不見這件事，寫成比例的會自動跟著縮放。')
    loan_wan = st.number_input('打算借多少（萬元）', min_value=10.0, max_value=principal_wan,
                               step=50.0, value=min(300.0, principal_wan),
                               key='emergency_loan_wan')
    rates = [0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
    st.dataframe(pd.DataFrame({
        '年利率': [f'{r:.0%}' for r in rates],
        '一年利息': [wan(loan_wan * 10000 * r) or f'{loan_wan * 10000 * r:,.0f} 元' for r in rates],
        '佔首年生活費': [f'{interest_share(loan_wan * 10000, r, plan["spend"]):.0%}' for r in rates],
    }), hide_index=True, width='stretch')
    st.caption('**利息是確定的，你避開的損失是不確定的。** '
               '所以門檻要訂得比「預期報酬」保守，不是訂在打平的地方。'
               '未計稅與手續費；賣出有證交稅，質押沒有，這會再拉開兩者的差距。')

    _section('一個可用的決策順序，以及它的兩個皺摺',
             '**依當時的條件決定，而不是事先綁死** —— 到時候你握有的資訊比現在多。'
             '但條件要現在就寫下來。')
    st.markdown(
        '1. **質押**，若當時利率與額度都在你訂的門檻內。不動持股、不改結構、'
        '每年撥款照舊，而且可逆。\n'
        '2. **賣成長池換正2**，若借不到。不依賴任何人，代價是結構被改變、'
        '而且你是在壓力下買進槓桿。\n'
        '3. **直接賣成長池**。最簡單、零對手風險，'
        f'而且對生活費幾乎無感（每 100 萬只少 {wan(cost["growth"]) or "不到 1 萬"}）；'
        '代價全部記在期末資產上。')
    st.warning(
        '**皺摺一：醫療急用不等你跑完三步。** 質押從申請到撥款要時間，被拒絕之後再去賣股'
        '又是幾天。真正的突發可能週內就要錢 —— 所以這個順序需要一個**時間維度**，'
        '第一週的錢多半還是得有一小筆現金在外面，不是為了金額，是為了速度。\n\n'
        '**皺摺二：第二順位會讓你在市場壓力下買槓桿。** 如果借不到是因為市場緊張，'
        '那你走到第二步時正好是在買進 1.81 倍的部位。可能是絕佳進場點，也可能不是 —— '
        '重點是它該是個清醒的決定，而不是「流程走到這裡」。')
    st.success(
        '**不管上面怎麼選，有一件事現在就該做：把質押額度先開好。** '
        '額度開著沒動用不花錢，但它在你需要的那一刻值最多，'
        '而且現在談條件的位置 —— 資產漂亮、沒有急迫性 —— 比將來好得多。')

    with st.expander('這一頁的數字從哪裡來'):
        st.markdown(
            f'**現算的**：兩個池子的生活費代價、LTV 表、利息佔比 —— '
            '全部由本金與上方的費率推出來，改了就跟著變。這一頁不讀行情，所以不會有失敗路徑。\n\n'
            f'**實測的**（{MEASURED_PRESET}，{MEASURED_WINDOW}，以還原價格計）：'
            '抽走 300 萬之後的生活費變化、正2 在成長池裡的漂移、最大回撤、1.81 倍斜率。'
            '這些是**那一段歷史上的量測，不是預測**，而且那六年半是台股加上台積電／AI 的'
            '超級循環 —— 槓桿在趨勢市場佔便宜、在震盪市場吃虧，這個樣本幾乎沒有橫盤段。\n\n'
            '**無法驗證的**：台灣券商當前的質押利率與放款條件。'
            '專案研究裡的 3% 是假設，不是報價。這個數字會實質改變上面的排序。\n\n'
            '全部未計稅、費用與交易成本。此頁為教育性資訊，不構成投資建議。')
