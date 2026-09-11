import json
from unittest.mock import patch, Mock
import pandas as pd
import pytest
from insights import (MAX_OUTPUT_TOKENS, READ_TIMEOUT_SECONDS, ModelOutputError, allocation_facts, market_and_income_facts,
                      sharpe_facts,
                      build_payload, conclusions, correlation_pairs, model_note,
                      request_insight, stream_insight)


def test_conclusion_uses_percentage_points_and_drawdown_direction():
    text = conclusions(pd.Series({'a':20.,'b':40.,'等權重組合':25.}), pd.Series({'a':-5.,'b':-20.,'等權重組合':-10.}))
    assert '5.0 個百分點' in text[0]
    assert '1/2' in text[2]


def test_ai_response_and_failure():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'解讀'}}]}
    with patch('insights.requests.post', return_value=response) as post:
        assert request_insight('{}','test-model','test-token') == '解讀'
        assert post.call_args.kwargs['timeout'] == (5, READ_TIMEOUT_SECONDS)
        assert post.call_args.kwargs['json']['max_tokens'] == MAX_OUTPUT_TOKENS
        assert post.call_args.kwargs['json']['chat_template_kwargs'] == {'enable_thinking': False}
        response.json.return_value = {'choices':[]}
        with pytest.raises(IndexError):
            request_insight('{}','test-model','test-token')


def test_reasoning_model_empty_content_names_the_cause():
    """A model that spends its whole budget thinking must not look like a network error."""
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'','reasoning_content':'想了很久'}}]}
    with patch('insights.requests.post', return_value=response):
        with pytest.raises(ModelOutputError) as caught:
            request_insight('{}','some/reasoning-model','test-token')
    assert 'some/reasoning-model' in str(caught.value)
    # Still a ValueError, so existing callers keep catching it.
    assert isinstance(caught.value, ValueError)


def test_empty_content_without_reasoning_stays_generic():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':''}}]}
    with patch('insights.requests.post', return_value=response):
        with pytest.raises(ValueError) as caught:
            request_insight('{}','m','t')
    assert not isinstance(caught.value, ModelOutputError)


def test_correlation_pairs_are_distinct_and_skip_nan():
    corr = pd.DataFrame({'a':[1.,.5,float('nan')],'b':[.5,1.,.2],'c':[float('nan'),.2,1.]},
                        index=['a','b','c'])
    pairs = correlation_pairs(corr, lambda s: s.upper())
    assert sorted(pairs) == [(.2,'B','C'), (.5,'A','B')]


def test_payload_carries_periods_and_weights_without_recomputing():
    index = pd.date_range('2026-01-01', periods=4)
    daily = pd.DataFrame({'a':[.01]*4}, index=index)
    segment = pd.DataFrame({'a':[1.,2.,3.,4.]}, index=index)
    weights = pd.Series({'a':1.})
    payload = json.loads(build_payload(['結論'], [(.5,'A','B')], '還原價格', daily, segment, weights))
    assert payload['correlation_period'] == ['2026-01-01','2026-01-04',4]
    assert payload['portfolio_period'] == ['2026-01-01','2026-01-04',3]
    assert payload['weights'] == {'a':1.}
    assert payload['conclusions'] == ['結論']


def test_truncated_answer_is_marked_not_silently_complete():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'講到一半'},'finish_reason':'length'}]}
    with patch('insights.requests.post', return_value=response):
        out = request_insight('{}','m','t')
    assert out.startswith('講到一半')
    assert '未完整' in out


def test_complete_answer_has_no_marker():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'完整結論'},'finish_reason':'stop'}]}
    with patch('insights.requests.post', return_value=response):
        assert request_insight('{}','m','t') == '完整結論'


def _facts(weights):
    idx = pd.date_range('2026-01-01', periods=3)
    names = list(weights.index)
    segment = pd.DataFrame({n: [100., 110., 120.] for n in names}, index=idx)
    vol = pd.Series({**{n: 20. for n in names}, '組合': 15.})
    dd = pd.Series({**{n: -30. for n in names}, '組合': -20.})
    portfolio = pd.Series([1., 1.1, 1.2], index=idx)
    return allocation_facts(segment, weights, portfolio, vol, dd, '組合')


def test_equal_weights_give_effective_count_equal_to_holdings():
    """Effective count measures weight spread only; equal weights is its maximum."""
    f = _facts(pd.Series({'a': 1/3, 'b': 1/3, 'c': 1/3}))
    assert f['集中度']['HHI'] == round(1/3, 3)
    assert f['集中度']['有效持股檔數'] == 3.0
    assert f['集中度']['實際檔數'] == 3


def test_lopsided_weights_shrink_the_effective_count():
    f = _facts(pd.Series({'a': .8, 'b': .1, 'c': .1}))
    assert f['集中度']['最大單一比重%'] == 80.0
    assert f['集中度']['前二大合計%'] == 90.0
    assert f['集中度']['有效持股檔數'] < 2


def test_recovery_gain_always_exceeds_the_fall():
    """A -20% drawdown needs +25% back; the asymmetry must be handed over precomputed."""
    f = _facts(pd.Series({'a': .5, 'b': .5}))
    assert f['組合']['最大回撤%'] == -20.0
    assert f['組合']['回撤回復所需漲幅%'] == 25.0
    assert f['組合']['回撤回復所需漲幅%'] > abs(f['組合']['最大回撤%'])


def test_volatility_gap_compares_blend_against_weighted_average():
    f = _facts(pd.Series({'a': .5, 'b': .5}))
    assert f['組合']['年化波動%'] == 15.0
    assert f['組合']['加權個別波動%'] == 20.0
    assert f['組合']['波動差距_百分點'] == 5.0


def test_holdings_are_ordered_by_weight():
    f = _facts(pd.Series({'small': .2, 'big': .5, 'mid': .3}))
    assert [h['標的'] for h in f['持股']] == ['big', 'mid', 'small']


def test_sharpe_facts_keeps_portfolio_separate_from_holdings():
    idx = pd.date_range('2025-01-01', periods=60, freq='B')
    rising = [100 * (1.001 ** i) for i in range(60)]
    flat = [100.0] * 60
    segment = pd.DataFrame({'a.TW': rising, 'b.TW': flat}, index=idx)
    facts = sharpe_facts(segment, pd.Series({'a.TW': .5, 'b.TW': .5}), 2.0,
                         {'a.TW': 'A 甲', 'b.TW': 'B 乙'}, '組合')['風險調整後報酬']
    assert facts['無風險年利率假設%'] == 2.0
    assert set(facts['各標的夏普比率']) == {'A 甲', 'B 乙'}
    assert '組合' not in facts['各標的夏普比率']
    # A zero-volatility holding cannot have a Sharpe; it must be None, not 0.
    assert facts['各標的夏普比率']['B 乙'] is None
    assert facts['組合夏普比率'] is not None


def _sse(*events):
    """Fake the router's server-sent event stream, terminator included."""
    lines = [b'data: ' + json.dumps(e).encode() for e in events]
    response = Mock()
    response.iter_lines.return_value = lines + [b'', b'data: [DONE]']
    return response


def test_stream_yields_pieces_in_order():
    events = [{'choices':[{'delta':{'content':'組合'}}]},
              {'choices':[{'delta':{'content':'高度集中'}}]},
              {'choices':[{'delta':{},'finish_reason':'stop'}]}]
    with patch('insights.requests.post', return_value=_sse(*events)) as post:
        assert list(stream_insight('{}','m','t')) == ['組合','高度集中']
        assert post.call_args.kwargs['json']['stream'] is True
        assert post.call_args.kwargs['stream'] is True


def test_stream_appends_marker_when_cut_short():
    events = [{'choices':[{'delta':{'content':'講到一半'}}]},
              {'choices':[{'delta':{},'finish_reason':'length'}]}]
    with patch('insights.requests.post', return_value=_sse(*events)):
        out = list(stream_insight('{}','m','t'))
    assert out[0] == '講到一半'
    assert '未完整' in out[-1]


def test_stream_of_pure_reasoning_names_the_cause():
    events = [{'choices':[{'delta':{'reasoning_content':'想了很久'}}]},
              {'choices':[{'delta':{},'finish_reason':'length'}]}]
    with patch('insights.requests.post', return_value=_sse(*events)):
        with pytest.raises(ModelOutputError):
            list(stream_insight('{}','some/model','t'))


def test_stream_skips_malformed_chunks_without_dying():
    """A truncated or non-JSON frame must not abort a reading that is otherwise fine."""
    response = Mock()
    response.iter_lines.return_value = [
        b'data: {"choices":[{"delta":{"content":"good"}}]}',
        b'data: {not json',
        b': keep-alive comment',
        b'data: {"choices":[{"delta":{"content":"tail"},"finish_reason":"stop"}]}',
        b'data: [DONE]']
    with patch('insights.requests.post', return_value=response):
        assert list(stream_insight('{}','m','t')) == ['good','tail']


def test_one_failing_source_does_not_hide_the_other():
    """A dividend outage must not also silence Beta, and the gap must be declared."""
    with patch('insights.beta_facts', return_value={'市場敏感度': {'基準': '0050'}}),          patch('insights.dividend_facts', side_effect=RuntimeError('provider down')):
        facts = market_and_income_facts(None, None, str, None, None, '還原', '組合', None)
    assert facts['市場敏感度'] == {'基準': '0050'}
    assert '配息' in facts['資料缺漏']
    assert 'Beta' not in facts['資料缺漏']


def test_both_sources_failing_is_stated_not_silent():
    with patch('insights.beta_facts', side_effect=RuntimeError),          patch('insights.dividend_facts', side_effect=RuntimeError):
        facts = market_and_income_facts(None, None, str, None, None, '還原', '組合', None)
    assert 'Beta' in facts['資料缺漏'] and '配息' in facts['資料缺漏']


def test_no_failures_adds_no_gap_notice():
    with patch('insights.beta_facts', return_value={'市場敏感度': {}}),          patch('insights.dividend_facts', return_value={'配息': {}}):
        facts = market_and_income_facts(None, None, str, None, None, '還原', '組合', None)
    assert '資料缺漏' not in facts


def test_custom_prompt_reaches_the_request():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'x'}}]}
    with patch('insights.requests.post', return_value=response) as post:
        request_insight('{}', 'm', 't', prompt='自訂指示')
    sent = post.call_args.kwargs['json']['messages'][0]
    assert sent['role'] == 'system'
    assert sent['content'] == '自訂指示'


def test_default_prompt_is_used_when_none_given():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'x'}}]}
    with patch('insights.requests.post', return_value=response) as post:
        request_insight('{}', 'm', 't')
    assert '## 分析框架' in post.call_args.kwargs['json']['messages'][0]['content']


def test_model_note_ignores_the_routing_suffix():
    assert model_note('zai-org/GLM-4.7-Flash:fastest') == model_note('zai-org/GLM-4.7-Flash')
    assert model_note('zai-org/GLM-4.7-Flash:cheapest') is not None
    assert model_note('some/unknown-model') is None
