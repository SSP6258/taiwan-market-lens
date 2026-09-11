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
