import pytest
import allocation
from allocation import validate_weights
from streamlit.testing.v1 import AppTest


def test_invalid_and_valid_weights():
    assert validate_weights([80,20]).tolist() == [.8,.2]
    for values in ([80,30], [-10,110], [float('nan'),100]):
        with pytest.raises(ValueError):
            validate_weights(values)


def test_shared_configuration_and_portfolio_beta():
    app = AppTest.from_string('''
import streamlit as st
import pandas as pd
import numpy as np
from allocation import allocation_picker
from beta_analysis import render_beta
p=pd.DataFrame(100*np.cumprod(1+np.random.default_rng(4).normal(0,.01,(90,2)),axis=0),index=pd.bdate_range('2025-01-01',periods=90),columns=['0050.TW','2330.TW'])
with st.sidebar:
    w,n=allocation_picker(list(p),str)
render_beta(p,str,list(p),p.index[0].date(),p.index[-1].date(),'收盤價',w,n)
''').run(timeout=30)
    assert not app.exception
    app.number_input[0].set_value(100.)
    app.number_input[1].set_value(0.)
    app.button(key='apply_weights').click().run(timeout=30)
    assert not app.exception
    row = app.dataframe[0].value.set_index('標的').loc['自訂配置組合']
    assert row['Beta'] == pytest.approx(1)
    assert row['R²'] == pytest.approx(1)
    app.number_input[0].set_value(90.)
    app.button(key='apply_weights').click().run(timeout=30)
    assert app.error
    assert app.session_state.applied_weights == [1.,0.]
    app.button(key='reset_weights').click().run(timeout=30)
    assert app.session_state.applied_weights == [.5,.5]


def test_presets_switch_symbols_weights_and_amount():
    app = AppTest.from_string("""
import streamlit as st
from allocation import preset_picker, allocation_picker
preset_picker()
st.multiselect('標的', st.session_state.symbol_options, key='chosen_named_symbols')
w, name = allocation_picker(st.session_state.chosen_named_symbols, str)
st.number_input('金額', key='investment_amount_wan')
""").run()
    assert not app.exception
    assert app.session_state.chosen_named_symbols == ['0050.TW', '2330.TW', '2454.TW']
    assert app.session_state.applied_weights == pytest.approx([1/3]*3)
    assert app.session_state.investment_amount_wan == 1000
    app.selectbox(key='portfolio_preset').select('退休1').run()
    assert not app.exception
    assert app.session_state.chosen_named_symbols == ['009816.TW', '00662.TW', '00984B.TWO', '00685L.TW']
    assert app.session_state.applied_weights == [.2, .2, .5, .1]
    assert app.session_state.investment_amount_wan == 3000
    app.number_input(key='investment_amount_wan').set_value(42).run()
    assert app.session_state.investment_amount_wan == 42
    app.button(key='reapply_preset').click().run()
    assert not app.exception
    assert app.session_state.investment_amount_wan == 3000
    app.selectbox(key='portfolio_preset').select('衝刺').run()
    assert not app.exception
    assert app.session_state.applied_weights == pytest.approx([1/3]*3)
    assert app.session_state.investment_amount_wan == 1000


def test_every_preset_is_fully_allocated():
    """Hand-typed weight tables: a transposed digit would silently under- or
    over-allocate, and the app would still run."""
    for name, config in allocation.PRESETS.items():
        assert sum(config['weights'].values()) == pytest.approx(100), name


def test_a_preset_whose_holdings_are_all_outside_the_catalogue_still_applies():
    """退休5 is the first preset built entirely from symbols the shortcut list does not
    carry, so nothing is waiting in the options for it: apply_preset has to put them there
    or the multiselect drops the whole allocation on the way in."""
    from market import CATALOG
    holdings = list(allocation.PRESETS['退休5']['weights'])
    assert not [s for s in holdings if s in CATALOG], '前提變了：這些已經進了 CATALOG'
    app = AppTest.from_string("""
import streamlit as st
from allocation import preset_picker, allocation_picker
preset_picker()
st.multiselect('標的', st.session_state.symbol_options, key='chosen_named_symbols')
w, name = allocation_picker(st.session_state.chosen_named_symbols, str)
st.number_input('金額', key='investment_amount_wan')
""").run()
    app.selectbox(key='portfolio_preset').select('退休5').run()
    assert not app.exception
    assert app.session_state.chosen_named_symbols == holdings
    assert app.multiselect[0].value == holdings
    assert app.session_state.applied_weights == pytest.approx([.9, .1])
    assert app.session_state.investment_amount_wan == 3000


def test_the_dollar_preset_stands_in_for_the_one_with_no_history():
    """退休6 exists to be 退休5 over a period long enough to look at, so the two have to
    keep the same shape: the same weights on the same kinds of holding."""
    five, six = allocation.PRESETS['退休5'], allocation.PRESETS['退休6']
    assert list(five['weights'].values()) == list(six['weights'].values()) == [90.0, 10.0]
    assert five['amount_wan'] == six['amount_wan']
    growth_five, growth_six = list(five['weights'])[0], list(six['weights'])[0]
    from market import currency_of
    assert currency_of(growth_five) == 'TWD' and currency_of(growth_six) == 'USD'
    # The buffer is the same holding in both, so only the growth pool differs.
    assert list(five['weights'])[1] == list(six['weights'])[1]
    app = AppTest.from_string("""
import streamlit as st
from allocation import preset_picker, allocation_picker
preset_picker()
st.multiselect('標的', st.session_state.symbol_options, key='chosen_named_symbols')
w, name = allocation_picker(st.session_state.chosen_named_symbols, str)
st.number_input('金額', key='investment_amount_wan')
""").run()
    app.selectbox(key='portfolio_preset').select('退休6').run()
    assert not app.exception
    assert app.session_state.chosen_named_symbols == list(six['weights'])
    assert app.session_state.applied_weights == pytest.approx([.9, .1])

    # 退休7 is the third of the same shape, with Taiwan as the growth pool. It shares the
    # buffer with the other two, which is what lands it on the same window as 退休6.
    seven = allocation.PRESETS['退休7']
    assert list(seven['weights'].values()) == [90.0, 10.0]
    assert list(seven['weights'])[1] == list(five['weights'])[1], '緩衝池要是同一檔'
    assert currency_of(list(seven['weights'])[0]) == 'TWD'
    app.selectbox(key='portfolio_preset').select('退休7').run()
    assert not app.exception
    assert app.session_state.chosen_named_symbols == list(seven['weights'])
    assert app.session_state.applied_weights == pytest.approx([.9, .1])


def test_the_dropdown_says_which_presets_are_the_buffer_pool_rule():
    # The mark is the only thing on that line that tells a reader the preset follows a
    # withdrawal rule rather than being a basket to hold, so it has to be on all four of
    # them and on none of the rest.
    for name in allocation.BUFFER_PRESETS:
        assert '緩衝池' in allocation.preset_label(name), name
    for name in allocation.PRESETS:
        if name not in allocation.BUFFER_PRESETS:
            assert '緩衝池' not in allocation.preset_label(name), name


def test_marking_a_preset_did_not_cost_the_dropdown_what_it_already_said():
    # 衝刺 is the one applied on arrival and every preset carries its sum; adding a third
    # mark must not have pushed either of them off the line.
    assert allocation.preset_label('衝刺') == '衝刺（預設・1,000 萬）'
    assert allocation.preset_label('退休1') == '退休1（3,000 萬）'
    assert allocation.preset_label('退休8') == '退休8（緩衝池・3,000 萬）'


def test_the_backtest_runs_exactly_the_presets_the_sidebar_marks():
    # Two lists would let the sidebar mark one set and the 緩衝池退休法 page run another,
    # and nothing on either screen would show the disagreement.
    from retirement_strategy import BACKTEST_NOTES, BACKTEST_PRESETS, BUFFER_SYMBOL
    assert BACKTEST_PRESETS == allocation.BUFFER_PRESETS
    for name in allocation.BUFFER_PRESETS:
        assert name in allocation.PRESETS, name
        # Marked as this rule but not actually holding the buffer would mean the page
        # offers a preset it cannot split into two pools.
        assert BUFFER_SYMBOL in allocation.PRESETS[name]['weights'], name
        assert name in BACKTEST_NOTES, name
