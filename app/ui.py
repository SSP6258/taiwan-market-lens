"""Shared presentation pieces. Kept in one place so styling cannot drift per page."""
from html import escape

import streamlit as st

# Matches the callout investment.py has used for its period notice since before
# this module existed; every period notice now renders through here instead of
# repeating the markup.
_BANNER = ('background:#FCE4E6;color:#7F2635;border:1px solid #EFA9B2;'
           'border-radius:12px;padding:16px 20px;line-height:1.6')


def period_banner(title, detail):
    """Highlight which dates a figure covers.

    Every page slices a different window out of the same prices, so the period is
    the one thing a reader must check before comparing numbers across tabs.
    """
    st.html(f'<div style="{_BANNER}"><strong>{escape(str(title))}</strong>'
            f'<div style="margin-top:6px">{escape(str(detail))}</div></div>')


def wan(value):
    """The same figure read in 萬, the unit these amounts are actually spoken in.

    Nothing under one 萬: "0.1 萬" is harder to read than the full number it would sit
    beneath, which is the opposite of the point. One decimal below a hundred 萬, where
    rounding to whole 萬 would throw away a visible part of the figure.
    """
    scaled = value / 10000
    if abs(scaled) < 1:
        return None
    return f'{scaled:,.1f} 萬' if abs(scaled) < 100 else f'{scaled:,.0f} 萬'


def money_metric(card, title, value, **kwargs):
    """A NT$ card carrying its 萬 reading underneath.

    `delta` is the only second line a metric offers, so the arrow and colour are turned
    off to keep it reading as a caption rather than as a change against an earlier figure.
    """
    card.metric(title, f'NT$ {value:,.0f}', delta=wan(value),
                delta_color='off', delta_arrow='off', **kwargs)

def plain(text):
    """Text that must render as written, not as markdown.

    Streamlit renders LaTeX between a pair of dollar signs, so a message quoting
    two prices loses both signs and sets everything between them in a maths font.
    Escaping belongs here rather than in the message: a future message carrying a
    price should not have to know about it.
    """
    return str(text).replace('$', chr(92) + '$')


def unit_notice(found, label):
    """Say which series were put back onto a single unit, and which steps were left alone.

    Staying quiet would be worse than the bug it fixes: the figures on screen no longer
    match the raw source. The second line earns its place as much as the first -- a step
    nobody could name is still sitting on the chart, and the reader should not have to
    find it by being surprised.
    """
    if not found:
        return

    def shape(divisor):
        return ('分割 1:{:g}'.format(divisor) if divisor > 1
                else '反向分割 {:g}:1'.format(round(1 / divisor)))

    repaired = found.get('unit_breaks') or {}
    if repaired:
        st.caption('已自動校正資料來源未記錄的分割（依單日跳動幅度與整數比例判定）：'
                   + '、'.join('{}：{:%Y/%m/%d} {}'.format(label(s), when, shape(d))
                               for s, items in repaired.items() for when, d in items)
                   + '。斷點之前的價格已換算為目前的計價單位。')
    converted = found.get('converted') or {}
    if converted:
        st.caption('下列標的以美元計價，已按當日匯率換算為新臺幣，**報酬因此包含匯率變動**：'
                   + '、'.join(label(s) for s in converted)
                   + '。與美元帳戶對帳單的數字會不同，差額就是台幣的升貶。')
    suspects = found.get('unit_suspects') or {}
    if suspects:
        st.caption('下列日期的價格跳動超過市場可能的幅度，但比例不是整數，'
                   '可能是除權配股或其他股權變動。**未做任何校正**，'
                   '涵蓋該日期的區間報酬與回撤可能失真：'
                   + '、'.join('{}：{:%Y/%m/%d} 比例 {:.2f}'.format(label(s), when, f)
                               for s, items in suspects.items() for when, f in items) + '。')


_ALLOCATION = ('font-size:13px;line-height:1.9', 'color:#94a3b8;font-size:12px;'
               'letter-spacing:.5px;margin-bottom:6px',
               'display:flex;gap:10px;justify-content:space-between;align-items:baseline',
               'overflow-wrap:anywhere', 'font-variant-numeric:tabular-nums;white-space:nowrap')


def allocation_card(title, rows):
    """One allocation on its own: holdings down the card, weight against each.

    The weight is pushed to the right edge rather than trailing the name, so the column of
    figures lines up and can be read without the names getting in the way.
    """
    body, heading, row, name, value = _ALLOCATION
    items = ''.join(f'<div style="{row}"><span style="{name}">{escape(str(n))}</span>'
                    f'<span style="{value}">{escape(str(v))}</span></div>' for n, v in rows)
    st.html(f'<div style="{body}"><div style="{heading}">{escape(str(title))}</div>{items}</div>')
