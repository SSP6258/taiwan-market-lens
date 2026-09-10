from unittest.mock import patch, Mock
import pandas as pd
import pytest
from insights import conclusions, request_insight


def test_conclusion_uses_percentage_points_and_drawdown_direction():
    text = conclusions(pd.Series({'a':20.,'b':40.,'等權重組合':25.}), pd.Series({'a':-5.,'b':-20.,'等權重組合':-10.}))
    assert '5.0 個百分點' in text[0]
    assert '1/2' in text[2]


def test_ai_response_and_failure():
    response = Mock()
    response.json.return_value = {'choices':[{'message':{'content':'解讀'}}]}
    with patch('insights.requests.post', return_value=response) as post:
        assert request_insight('{}','test-model','test-token') == '解讀'
        assert post.call_args.kwargs['timeout'] == (5,30)
        response.json.return_value = {'choices':[]}
        with pytest.raises(IndexError):
            request_insight('{}','test-model','test-token')
