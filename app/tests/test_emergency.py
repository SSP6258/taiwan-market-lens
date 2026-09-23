import pytest
from emergency import (STRESS_DROPS, WARNING_LTV, income_cost_per_million, interest_share,
                       ltv_after, ltv_table)


def test_the_two_pools_cost_one_to_twenty_five():
    """The page's headline ratio. Derived from the rates, never written down: the growth
    pool reaches the wallet through a transfer and then a withdrawal, the buffer is
    already one step away, and the gap between those is the whole point of the page."""
    cost = income_cost_per_million(transfer_rate=0.04, withdraw_rate=0.25)
    assert cost['growth'] == pytest.approx(10_000)
    assert cost['buffer'] == pytest.approx(250_000)
    assert cost['buffer'] / cost['growth'] == pytest.approx(25)
    # Move the rate the page lets the reader move, and the ratio has to move with it.
    slower = income_cost_per_million(transfer_rate=0.01, withdraw_rate=0.25)
    assert slower['buffer'] / slower['growth'] == pytest.approx(100)
    assert slower['buffer'] == cost['buffer'], '領出率沒動，緩衝池的代價就不該動'


def test_the_ltv_table_survives_the_crash_it_claims_to():
    """Every row that says it holds through a drop has to actually hold through it -- the
    claim is the reason someone would size a loan that way."""
    table = ltv_table(30_000_000)
    for _, row in table.iterrows():
        deepest = row['撐得住的最深跌幅']
        if not deepest:
            continue
        assert ltv_after(row['起始 LTV'], deepest) < WARNING_LTV
        # And it must be the deepest one that holds, not merely one that does.
        deeper = [d for d in STRESS_DROPS if d > deepest]
        assert all(ltv_after(row['起始 LTV'], d) >= WARNING_LTV for d in deeper)


def test_the_loan_column_follows_the_principal():
    assert ltv_table(30_000_000)['可借金額'].tolist() == pytest.approx(
        [30_000_000 * s for s in ltv_table(30_000_000)['起始 LTV']])
    small = ltv_table(10_000_000)
    assert small['可借金額'].iloc[0] == pytest.approx(1_000_000)
    # The percentages are ratios, so they must NOT move with the principal.
    assert small['跌 50% 後'].tolist() == pytest.approx(ltv_table(30_000_000)['跌 50% 後'].tolist())


def test_the_interest_line_scales_with_the_loan():
    """Expressed against income precisely so it scales -- a bare rate cannot see either
    a bigger loan or a leaner year."""
    spend = 1_020_000.
    assert interest_share(3_000_000, .03, spend) == pytest.approx(90_000 / spend)
    assert interest_share(6_000_000, .03, spend) == pytest.approx(
        2 * interest_share(3_000_000, .03, spend))
    assert interest_share(3_000_000, .06, spend) == pytest.approx(
        2 * interest_share(3_000_000, .03, spend))
    # A year with no income would divide by zero rather than print a number.
    assert interest_share(3_000_000, .03, 0) != interest_share(3_000_000, .03, 0)
