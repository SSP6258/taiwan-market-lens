import pytest
from emergency import SAFE_DROP, SAFE_LTV, WARNING_LTV, income_cost_per_million


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


def test_the_borrowing_rule_of_thumb_holds_through_the_crash_it_names():
    """The page says borrow under SAFE_LTV and a SAFE_DROP fall stays under the warning
    line. That sentence is only worth printing if the arithmetic behind it is true."""
    assert SAFE_LTV / (1 - SAFE_DROP) < WARNING_LTV
    # And the named fall is far past anything measured: 退休8's worst was -22.3%.
    assert SAFE_DROP > 0.223 * 2
