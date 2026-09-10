import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st


def validate_weights(values):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or not np.isclose(values.sum(), 100, atol=0.00001, rtol=0):
        raise ValueError('比重合計必須為 100.0%，且每檔不得為負值。原配置未變更。')
    return values / 100


def allocation_picker(symbols, label):
    identity = tuple(symbols)
    changed = st.session_state.get('allocation_symbols') != identity
    if changed:
        had = 'allocation_symbols' in st.session_state
        st.session_state.allocation_symbols = identity
        st.session_state.applied_weights = [1 / len(symbols)] * len(symbols)
        st.session_state.allocation_custom = False
        # Tenths sum exactly to 100.0 in the editable draft.
        for i, s in enumerate(symbols):
            st.session_state['weight_' + s] = (1000 // len(symbols) + (i < 1000 % len(symbols))) / 10
        local_file = Path(__file__).with_name('local_portfolio.json')
        if not had and local_file.exists():
            config = json.loads(local_file.read_text(encoding='utf-8'))
            if set(config.get('weights', {})) == set(symbols):
                local_weights = validate_weights([config['weights'][s] for s in symbols])
                st.session_state.applied_weights = local_weights.tolist()
                st.session_state.allocation_custom = True
                for s in symbols:
                    st.session_state['weight_' + s] = float(config['weights'][s])
                if 'investment_amount_wan' not in st.session_state:
                    st.session_state.investment_amount_wan = float(config['amount_wan'])
        if had:
            st.info('可用標的已變更，配置已恢復等權重。')
    with st.expander('組合配置｜' + ('自訂' if st.session_state.allocation_custom else '等權重'), expanded=False):
        st.caption('修改後點「套用配置」。比重是起始投入比例，之後持有、不再平衡。0.0% 不投入，但仍保留在比較清單與共同期間計算。')
        if st.button('恢復等權重', key='reset_weights'):
            st.session_state.applied_weights = [1 / len(symbols)] * len(symbols)
            st.session_state.allocation_custom = False
            for i, s in enumerate(symbols):
                st.session_state['weight_' + s] = (1000 // len(symbols) + (i < 1000 % len(symbols))) / 10
        values = [st.number_input(label(s) + ' (%)', min_value=0.0, max_value=100.0, step=0.1, format='%.1f', key='weight_' + s) for s in symbols]
        st.caption(f'編輯中合計：{sum(values):.1f}% · 套用前結果維持原配置')
        if st.button('套用配置', type='primary', key='apply_weights'):
            try:
                st.session_state.applied_weights = validate_weights(values).tolist()
                st.session_state.allocation_custom = True
                st.success('已套用配置。')
            except ValueError as exc:
                st.error(str(exc))
    weights = pd.Series(st.session_state.applied_weights, index=symbols)
    name = '自訂配置組合' if st.session_state.allocation_custom else '等權重組合'
    st.caption('目前配置：' + '、'.join(f'{s.split(".")[0]} {weights[s]*100:.1f}%' for s in symbols))
    return weights, name
