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
