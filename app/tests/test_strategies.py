"""Comparing whole allocations only means something if they share one window."""
import pandas as pd
import pytest


def _prices():
    """b lists two months late, so any configuration holding it sets the shared start."""
    index = pd.date_range('2026-01-01', periods=6, freq='D')
    return pd.DataFrame({
        'a': [100., 110., 121., 133.1, 146.41, 161.051],
        'b': [float('nan'), float('nan'), 100., 90., 99., 108.9],
        'c': [50., 55., 60., 55., 60., 66.],
    }, index=index)


def test_every_configuration_is_measured_over_the_same_window():
    """A configuration made only of long-history holdings must still be cut back to the
    window the others can reach; otherwise it is credited with returns the rest never had
    the chance to earn."""
    from strategies import configuration_paths
    allocations = {'old': pd.Series({'a': 1.0}), 'young': pd.Series({'b': 1.0})}
    paths = configuration_paths(_prices(), allocations)
    assert list(paths.columns) == ['old', 'young']
    assert str(paths.index[0].date()) == '2026-01-03'
    assert len(paths) == 4
    # Each path starts at 1.0 on that shared day, so the lines start together.
    assert (paths.iloc[0] == 1.0).all()
    # 'old' over the shared window only: 161.051/121, not 161.051/100.
    assert round(paths['old'].iloc[-1], 4) == round(161.051 / 121, 4)


def test_dropping_the_late_holding_lengthens_the_window():
    """The reason the page names the binding holding: removing it buys back history."""
    from strategies import configuration_paths
    paths = configuration_paths(_prices(), {'old': pd.Series({'a': 1.0}), 'other': pd.Series({'c': 1.0})})
    assert str(paths.index[0].date()) == '2026-01-01'
    assert len(paths) == 6


def test_binding_holding_names_who_is_paying_for_it():
    from strategies import binding_holding
    allocations = {'x': pd.Series({'a': .5, 'b': .5}), 'y': pd.Series({'a': 1.0}),
                   'z': pd.Series({'b': 1.0})}
    symbol, began, holders = binding_holding(_prices(), allocations)
    assert symbol == 'b'
    assert str(began.date()) == '2026-01-03'
    assert holders == ['x', 'z']


def test_nothing_binds_when_every_holding_starts_together():
    from strategies import binding_holding
    assert binding_holding(_prices(), {'y': pd.Series({'a': .5, 'c': .5})}) is None


def test_a_missing_quote_is_named_rather_than_quietly_dropped():
    from strategies import configuration_paths
    with pytest.raises(ValueError, match='缺少行情'):
        configuration_paths(_prices(), {'x': pd.Series({'a': .5, 'zz': .5})})
