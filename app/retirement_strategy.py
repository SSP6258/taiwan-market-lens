"""What the 退休5／退休6 presets actually do, and why each number in the rule is that number.

The rule is a dynamic withdrawal: every year a fixed share of the growth pool is moved into
a buffer, and a fixed share of the buffer is spent. Nothing here is a forecast; the figures
quoted against the design come from the simulations recorded in WORKLOG 第四十、四十一次.
"""
from pathlib import Path

import streamlit as st

from allocation import PRESETS
from ui import wan

# The two knobs of the rule. They are constants rather than inputs because the whole page
# explains why these particular values hold together; a slider would invite reading the
# arithmetic as a recommendation to tune them.
TRANSFER_RATE = 0.04   # moved out of the growth pool each year
WITHDRAW_RATE = 0.25   # taken out of the buffer each year, i.e. a quarter

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


def growth_share(shape):
    """The growth pool's share of the whole, read off the preset rather than restated here."""
    if shape == ORIGINAL:
        return 100 / 112
    weights = PRESETS['退休5']['weights']
    return max(weights.values()) / sum(weights.values())


def pool_plan(principal, share):
    """One year of the rule, from a principal to the money that reaches the wallet.

    Returned as a dict rather than a tuple: every one of these figures appears on the page
    with its own explanation, and positional unpacking would make that easy to get wrong.
    """
    growth = principal * share
    buffer = principal - growth
    transfer = growth * TRANSFER_RATE
    pooled = buffer + transfer
    spend = pooled * WITHDRAW_RATE
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


def _caption(card, title, value, note):
    card.metric(title, value, delta=note, delta_color='off', delta_arrow='off')


def render_strategy():
    st.subheader('緩衝池退休法：成長池 ＋ 緩衝池')
    st.markdown(
        '**不是每年固定領多少錢，而是每年領走資產的一個比例。** 因為永遠只拿走一部分，'
        '這種規則在定義上不會把錢領到見底 —— 代價是收入會跟著市場上下。'
        '緩衝池的唯一工作，就是把那個上下壓平到能過日子的幅度。')

    if POSTER.exists():
        st.image(str(POSTER),
                 caption='策略說明圖：原始設計 100：12（出自 analysis/，不是 APP 預設的 90：10）')
    else:
        st.info('策略說明圖不在預期位置（`analysis/retirement5-original-100-12.png`）。'
                '下面的文字與試算不受影響。')

    st.markdown('### 一年只做兩個動作')
    st.markdown(
        '1. **從成長池撥出當時市值的 4%**，放進緩衝池。剩下的 96% 繼續投資，不動。\n'
        '2. **從緩衝池領出 25%** 當今年的生活費 —— 這一步決定的是**今年的總額**，'
        '不是非得一次領完（見下方「執行面」）。剩下的 75% 留著，繼續當緩衝。\n\n'
        '合起來就是：**年生活費 ＝（成長池 × 4% ＋ 緩衝池）× 25%**')

    st.markdown('### 換成你的金額')
    left, right = st.columns(2)
    principal_wan = left.number_input(
        '本金（萬元）', min_value=100.0, max_value=100000.0, step=100.0,
        value=float(PRESETS['退休5']['amount_wan']), key='retirement_principal_wan')
    # The preset comes first: this page exists to explain what the app actually does, and
    # the poster above it is captioned as the other ratio.
    shape = right.radio('配置比例', [PRESET, ORIGINAL], key='retirement_shape',
                        help='APP 的退休5／退休6 用比較好記的 90：10；圖上畫的是原始的 100：12，'
                             '兩者的首年生活費差約 5 萬。')
    share = growth_share(shape)
    plan = pool_plan(principal_wan * 10000, share)

    cards = st.columns(4)
    _caption(cards[0], '成長池', wan(plan['growth']), f'{share:.1%}')
    _caption(cards[1], '緩衝池', wan(plan['buffer']), f'{1 - share:.1%}')
    _caption(cards[2], '首年生活費', wan(plan['spend']), f'佔本金 {plan["spend_rate"]:.3%}')
    _caption(cards[3], '平均每月', wan(plan['monthly']), '總額 ÷ 12，未計稅與費用')

    st.markdown(
        '| 步驟 | 算式 | 結果 |\n|---|---|---|\n'
        f'| 成長池撥出 | {wan(plan["growth"])} × 4% | {wan(plan["transfer"])} |\n'
        f'| 撥入後的緩衝池 | {wan(plan["buffer"])} ＋ {wan(plan["transfer"])} | {wan(plan["pooled"])} |\n'
        f'| 今年生活費 | {wan(plan["pooled"])} × 25% | **{wan(plan["spend"])}** |\n'
        f'| 留在緩衝池 | {wan(plan["pooled"])} × 75% | {wan(plan["buffer_left"])} |\n'
        f'| 留在成長池 | {wan(plan["growth"])} × 96% | {wan(plan["growth_left"])} |\n')
    st.caption(f'緩衝池的存量相當於 {plan["buffer_years"]:.2f} 年的生活費。')

    gain = monthly_execution_gain(plan['spend'])
    st.markdown('### 執行面：金額一年決定一次，動用可以分月')
    st.markdown(
        '**撥款是一年一次的動作。** 在那一天用當時的市值算出撥出額與今年的生活費總額，'
        '算完就固定了，接下來一整年不再隨市場變動。\n\n'
        '**但「領出來」不必一次領完。** 把總額分成十二份逐月動用，效果是一樣的，'
        '而且還沒動用的部分留在緩衝池裡繼續生息。以 00865B 實測年化 2.89% 估，'
        f'分月動用比年初一次領出大約多 **{wan(gain)}**／年'
        f'（約等於生活費的 {gain / plan["spend"]:.1%}）—— 金額不大，但方向對你有利。\n\n'
        '**這也表示模擬的結果偏保守。** 下面引用的模擬是在年初把整年生活費一次扣掉、'
        '之後才套用當年報酬，等於假設這筆錢整年都沒在賺錢。實際分月動用會比模擬略好一點。')
    st.warning('**分月動用不等於每月重算。** 每個月只是把年初算好的總額取出十二分之一；'
               '若改成每個月重新計算一次「緩衝池的 25%」，那是完全不同的規則 —— '
               '一年會領走緩衝池的 96.8%（1 − 0.75¹²），緩衝立刻消失。'
               '**25% 是年度比率，不是月度比率。**')

    st.markdown('### 每個數字為什麼是那個數字')
    st.markdown(
        '**4% —— 撥出率，決定生活費的水準。** 它不是報酬率，也不是「安全提領率」，'
        '而是你每年從成長池搬多少到花得到的地方。這個數字調高，生活費整條曲線往上移；'
        '但調到 7% 就會出現吃本金的訊號 —— 模擬裡第 40 年的收入反而低於第 20 年。\n\n'
        '**25% —— 領出比例，也就是四分之一。** 領四分之一的意思是，緩衝池裡的每一塊錢'
        '平均要花四年。這是把「今年市場的好壞」攤開到好幾年的動作，也是整個設計的核心。\n\n'
        '**12 ÷ 4 ＝ 3 —— 緩衝池正好是三年的提領量，這就是 100：12 的由來。**'
        '三年是典型的緩衝設計：足以撐過一次常見的空頭，又不至於放太多錢在低報酬的短債上。\n\n'
        '**這個組合讓第一年進出剛好打平，不是巧合。** 緩衝池 12 份加上今年撥入的 4 份等於 16 份，'
        '取 25% 正好是 4 份 —— 等於撥入量。寫成代數就是 **（G × 4% ＋ B）× 25% ≡ G × 4%**，'
        '在 B 等於三倍撥出量時成立。所以緩衝池不會被自己的規則慢慢抽乾。')

    st.markdown(
        '**留下 75% 帶來的平滑，才是緩衝池真正在做的事。** 忽略短債報酬與費用，'
        '整條規則可以化簡成一句話：\n\n'
        '> **今年生活費 ＝ 去年生活費 × 75% ＋ 今年撥款 × 25%**\n\n'
        '今年的市場只影響生活費的四分之一。圖上那個例子就是這件事：'
        '成長池由 100 跌到 60、緩衝池維持 12，生活費從 4 降到 3.6 —— '
        '**股票跌 40%，生活費只降 10%。**')

    st.markdown('### 為什麼不需要再平衡')
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

    st.markdown('### 這個設計買到了什麼')
    st.markdown(
        '| 項目 | 緩衝池法 | 對照 |\n|---|---|---|\n'
        '| 最差的單年收入 | **−12.9%** | 沒有緩衝池：−37.1% |\n'
        '| 組合存續期間 | **0.21 年** | 退休1（含長債）：7.00 年 |\n'
        '| 2022 股債同跌 | **−9.8%** | 退休1：−16.6% |\n'
        '| 需要質押借款 | **零** | 退休1：每年約 56 萬 |\n'
        '| 通膨 5% 下第 40 年實質收入 | 334 萬（2% 時 339 萬） | 退休1 斷頭機率 5.1% → 19.0% |\n')
    st.caption('最差單年收入那兩欄是同樣資產、同樣提領率，只差有沒有緩衝池。'
               '存續期間短代表升息造成的帳面損失小 —— 這一項與抗通膨其實是同一個曝險的兩面。')
