import pytest
from allocation import PRESETS
from retirement_strategy import ORIGINAL, POSTER, PRESET, growth_share, pool_plan


def test_the_original_ratio_pays_out_exactly_what_it_moved_in():
    """100:12 is not an arbitrary split: the buffer holds three years of spending, so the
    year's transfer and the year's withdrawal are the same number and the buffer holds."""
    plan = pool_plan(3000 * 10000, growth_share(ORIGINAL))
    assert plan["spend"] == pytest.approx(plan["transfer"])
    assert plan["buffer_years"] == pytest.approx(3.0)
    assert plan["buffer_left"] == pytest.approx(plan["buffer"])
    assert plan["spend"] / 10000 == pytest.approx(107.14, abs=0.01)   # the figure on the poster
    assert plan["monthly"] / 10000 == pytest.approx(8.93, abs=0.01)


def test_the_preset_ratio_is_read_off_the_preset_not_restated():
    """The page must follow 退休5 if its weights are ever edited, rather than drift from it."""
    assert growth_share(PRESET) == pytest.approx(PRESETS["退休5"]["weights"]["009826.TW"] / 100)
    plan = pool_plan(3000 * 10000, growth_share(PRESET))
    assert plan["growth"] / 10000 == pytest.approx(2700)
    assert plan["buffer"] / 10000 == pytest.approx(300)
    assert plan["spend"] / 10000 == pytest.approx(102)


def test_the_rounder_ratio_leaves_the_buffer_a_little_short_of_three_years():
    """90:10 spends slightly less than it moves in, so the buffer creeps up rather than down.
    Worth pinning: it is the difference between the poster and what the app actually presets."""
    plan = pool_plan(3000 * 10000, growth_share(PRESET))
    assert plan["spend"] < plan["transfer"]
    assert plan["buffer_left"] > plan["buffer"]
    assert plan["buffer_years"] == pytest.approx(2.94, abs=0.01)


def test_nothing_is_created_or_lost_in_a_year():
    plan = pool_plan(3000 * 10000, growth_share(ORIGINAL))
    assert plan["growth_left"] + plan["buffer_left"] + plan["spend"] == pytest.approx(3000 * 10000)


def test_the_spending_rate_scales_with_the_principal_but_the_share_does_not():
    small, large = pool_plan(1000 * 10000, 0.9), pool_plan(9000 * 10000, 0.9)
    assert large["spend"] == pytest.approx(small["spend"] * 9)
    assert large["spend_rate"] == pytest.approx(small["spend_rate"])


def test_an_empty_principal_does_not_divide_by_zero():
    plan = pool_plan(0, growth_share(ORIGINAL))
    assert plan["spend"] == 0
    assert plan["buffer_years"] != plan["buffer_years"]   # NaN, not a crash


def test_the_poster_the_page_shows_is_still_where_the_page_looks():
    """The page degrades to a notice if it is gone, which is easy not to notice. It lives in
    analysis/ with the study that produced it, so it is a runtime asset of the app as well."""
    assert POSTER.exists(), POSTER
    assert POSTER.stat().st_size > 100_000
