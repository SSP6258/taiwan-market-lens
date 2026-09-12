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
