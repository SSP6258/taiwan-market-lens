import pytest
from ui import wan


def test_wan_reads_the_figure_in_the_unit_people_speak():
    assert wan(43201921) == '4,320 萬'
    assert wan(30000000) == '3,000 萬'
    # Below a hundred 萬 a whole-萬 rounding would hide a visible part of the figure.
    assert wan(234567) == '23.5 萬'
    assert wan(-4320000) == '-432 萬'
    assert wan(-234567) == '-23.5 萬'


def test_wan_stays_quiet_under_one_wan():
    """A second line reading '0.1 萬' is harder to read than the NT$ figure above it."""
    assert wan(1100) is None
    assert wan(0) is None
    assert wan(-9999) is None
    assert wan(10000) == '1.0 萬'
