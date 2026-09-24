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


def test_the_mortgage_line_leads_and_says_it_has_a_deadline():
    """理財型房貸 is first for a reason the others cannot match -- its collateral is not
    marked to market, so a crash cannot withdraw it -- and it is the only one whose
    eligibility closes at retirement. A page that buried either would be worse than
    silent: the reader would set up the facility they can always get, and miss the one
    they cannot."""
    from emergency import PLAYBOOK
    assert PLAYBOOK[0]['名稱'] == '理財型房貸', [p['名稱'] for p in PLAYBOOK]
    assert '退休前' in PLAYBOOK[0]['關鍵']
    assert '不逐日' in PLAYBOOK[0]['為什麼排這裡'], '沒有逐日評價才是它排第一的理由'
    # It leads, so its cost has to be stated on the same row rather than left to a footnote.
    assert '住的地方' in PLAYBOOK[0]['代價']


def test_every_playbook_entry_states_what_it_costs():
    """Four options with no cost column would read as four free lunches."""
    from emergency import PLAYBOOK
    assert len(PLAYBOOK) == 5
    assert len({p['名稱'] for p in PLAYBOOK}) == 5
    for entry in PLAYBOOK:
        for field in ('名稱', '關鍵', '為什麼排這裡', '代價'):
            assert entry[field].strip(), (entry['名稱'], field)
    # 質押 ranks second, and the reason it is not first belongs next to it.
    assert PLAYBOOK[1]['名稱'] == '質押借款'
    assert '跟著市場跌' in PLAYBOOK[1]['代價']
    # 信貸 sits above 正2 for the same reason 質押 does -- it leaves the portfolio alone --
    # and below 質押 because it costs more. Its own cost is the repayment shape.
    assert PLAYBOOK[2]['名稱'] == '信用貸款'
    assert '本息攤還' in PLAYBOOK[2]['代價']
    assert PLAYBOOK[-1]['名稱'] == '直接賣成長池', '永遠可用的那個殿後'


def test_the_page_counts_its_own_playbook():
    """The heading said 四個 while the table showed five, the first time an entry was
    added. Both counts are derived now, so the drift cannot come back."""
    from emergency import PLAYBOOK, _numeral
    assert _numeral(len(PLAYBOOK)) == '五'
    assert _numeral(len(PLAYBOOK) - 1) == '四'
    # An unmapped count degrades to a digit rather than raising on a live page.
    assert _numeral(99) == '99'


def test_the_pledge_rates_are_quoted_not_assumed():
    """The project's 40-year study used 3%, which is below anything on offer. These are
    a broker's own figures, and they are per instrument -- a leveraged holding costs half
    again as much to borrow against, which matters to anyone who took option 4 first."""
    from emergency import OBSERVED_RATES, OBSERVED_SOURCE
    rates = dict(OBSERVED_RATES)
    assert min(rates.values()) >= 0.04, '沒有一檔低到專案假設的 3%'
    assert rates['槓桿型與期貨型'] > rates['一般股票型 ETF'] * 1.4
    # A quote with no date and no source is an assumption wearing better clothes.
    assert '2026-' in OBSERVED_SOURCE and '證券' in OBSERVED_SOURCE
