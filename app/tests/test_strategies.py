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


def _label(symbol):
    return symbol.upper()


def test_a_weight_reads_as_written_not_as_stored():
    """50% rather than 50.0%; a third of a portfolio still needs the decimal it has."""
    from strategies import percent
    assert percent(50.0) == '50%'
    assert percent(100 / 3) == '33.3%'
    assert percent(0.0) == '0%'
    assert percent(12.5) == '12.5%'


def test_a_configuration_lists_its_largest_position_first():
    from strategies import composition_rows
    rows = composition_rows(pd.Series({'a': .2, 'b': .5, 'c': .3}), str.upper)
    assert rows == [('B', '50%'), ('C', '30%'), ('A', '20%')]


def test_a_holding_set_to_zero_is_still_listed():
    """0% is a decision -- on the comparison list, no money in it. Dropping the row would
    make the configuration look like the holding was never considered."""
    from strategies import composition_rows
    rows = composition_rows(pd.Series({'a': 1.0, 'b': 0.0}), str.upper)
    assert rows == [('A', '100%'), ('B', '0%')]


def test_every_configuration_still_adds_up():
    """Each card is a whole allocation; the presets are typed by hand and a digit dropped
    here would show as a plausible-looking card that quietly invests less than everything."""
    from strategies import allocation_table
    for name, weights in allocation_table().items():
        assert round(weights.sum(), 9) == 1.0, name
