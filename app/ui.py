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
