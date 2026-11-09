"""Chart presentation rules. The palette lives in the chart module rather than inside the
page script so that the one reserved colour can actually be guarded by a test."""
import pandas as pd


def _frame():
    index = pd.date_range('2026-01-01', periods=3, freq='D')
    return pd.DataFrame({'a': [0., 1., 2.], 'blend': [0., .5, 1.]}, index=index)


def _series(emphasis):
    from lightweight_chart import chart_series
    frame = _frame()
    return {s['name']: s for s in chart_series(
        frame, {c: c for c in frame.columns}, {'a': '#3B9EFF', 'blend': '#FFFFFF'}, emphasis)}


def test_no_holding_colour_can_be_mistaken_for_the_blend():
    """A holding drawn in near-white read as a second blend line. Distance, not identity:
    #F5F7FA was never equal to #FFFFFF, it merely looked like it."""
    from lightweight_chart import COLORS, BLEND_COLOR
    def rgb(value):
        value = value.lstrip('#')
        return [int(value[i:i + 2], 16) for i in (0, 2, 4)]
    target = rgb(BLEND_COLOR)
    assert BLEND_COLOR not in COLORS
    for colour in COLORS:
        gap = sum((a - b) ** 2 for a, b in zip(rgb(colour), target)) ** .5
        assert gap > 90, f'{colour} is too close to the blend colour {BLEND_COLOR}'


def test_holdings_recede_only_when_a_blend_is_present():
    """Without a blend nothing is subordinate, so fading would just dim the whole chart."""
    alone = _series(None)
    assert all(s['line'] == s['color'] for s in alone.values())
    assert {s['width'] for s in alone.values()} == {2}


def test_the_blend_is_drawn_forward_and_the_holdings_back():
    with_blend = _series('blend')
    assert with_blend['blend']['line'] == '#FFFFFF' and with_blend['blend']['width'] == 3
    assert with_blend['a']['line'] == 'rgba(59,158,255,0.42)' and with_blend['a']['width'] == 2
    # The legend still carries the identity colour; only the canvas recedes.
    assert with_blend['a']['color'] == '#3B9EFF'


def test_each_holding_carries_its_close_and_the_blend_none():
    """The hover shows the day's quote beside the reading. The blend has no price of its
    own, so it must not borrow one; a holding missing from the closes shows none either."""
    from lightweight_chart import chart_series
    frame = _frame()
    closes = pd.DataFrame({'a': [10., 10.1, 10.2]}, index=frame.index)
    series = {s['name']: s for s in chart_series(
        frame, {c: c for c in frame.columns}, {'a': '#3B9EFF', 'blend': '#FFFFFF'}, 'blend', closes)}
    assert series['a']['prices'] == {'2026-01-01': 10., '2026-01-02': 10.1, '2026-01-03': 10.2}
    assert series['blend']['prices'] is None


def test_without_closes_no_series_claims_a_price():
    assert all(s['prices'] is None for s in _series(None).values())


def test_only_a_chart_that_asks_for_it_names_its_axis_readings(monkeypatch):
    """The configurations' axis readings carry their names; the holdings' do not, since a
    ticker is already in the legend and a name would crowd the column on a phone."""
    import lightweight_chart
    sent = []
    monkeypatch.setattr(lightweight_chart, '_component', lambda **kw: sent.append(kw['data']))
    frame = _frame()
    for named in (False, True):
        lightweight_chart.render_chart(frame, {c: c for c in frame.columns},
                                       {'a': '#3B9EFF', 'blend': '#FFFFFF'}, '累積漲跌幅', axis_names=named)
    assert [d['axis_names'] for d in sent] == [False, True]
