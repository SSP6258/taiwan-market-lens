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
    from emergency import BRIDGE
    assert BRIDGE[0]['名稱'] == '理財型房貸', [p['名稱'] for p in BRIDGE]
    assert '退休前' in BRIDGE[0]['關鍵']
    assert '不逐日' in BRIDGE[0]['為什麼排這裡'], '沒有逐日評價才是它排第一的理由'
    # It leads, so its cost has to be stated on the same row rather than left to a footnote.
    assert '住的地方' in BRIDGE[0]['代價']


def test_every_playbook_entry_states_what_it_costs():
    """Options with no cost column would read as free lunches."""
    from emergency import BRIDGE, PERMANENT
    names = [p['名稱'] for p in BRIDGE + PERMANENT]
    assert len(names) == len(set(names)) == 5, names
    for entry in BRIDGE + PERMANENT:
        for field in ('名稱', '關鍵', '為什麼排這裡', '代價'):
            assert entry[field].strip(), (entry['名稱'], field)
    # 質押 ranks second, and the reason it is not first belongs next to it.
    assert BRIDGE[1]['名稱'] == '質押借款'
    assert '跟著市場跌' in BRIDGE[1]['代價']
    # 信貸 is last of the loans: no margin call is all it offers, and selling has that too.
    assert BRIDGE[-1]['名稱'] == '信用貸款'
    assert '本息攤還' in BRIDGE[-1]['代價']


def test_money_that_is_not_coming_back_is_sold_for_not_borrowed():
    """2026-10-10: a loan against money that is not coming back is repaid by selling the
    growth pool anyway, later and with interest. So selling leads that path, 正2 follows
    as a way of doing the same sale, and no loan appears in it."""
    from emergency import BRIDGE, PERMANENT
    assert PERMANENT[0]['名稱'] == '直接賣成長池'
    assert '預設' in PERMANENT[0]['關鍵']
    assert all('賣成長池' in p['名稱'] for p in PERMANENT), [p['名稱'] for p in PERMANENT]
    assert any('正2' in p['名稱'] for p in PERMANENT[1:])
    assert not any('賣' in p['名稱'] for p in BRIDGE), '過渡清單只放借款'


def test_the_page_counts_its_own_playbook():
    """The heading said 四個 while the table showed five, the first time an entry was
    added. The count is derived now, so the drift cannot come back."""
    from emergency import BRIDGE, _numeral
    assert _numeral(len(BRIDGE)) == '三'
    # An unmapped count degrades to a digit rather than raising on a live page.
    assert _numeral(99) == '99'


def test_the_pledge_rates_are_quoted_not_assumed():
    """The project's 40-year study used 3%, which is below anything on offer. These are
    a broker's own figures, and they are per instrument -- a leveraged holding costs half
    again as much to borrow against, which matters to anyone who took the 正2 route first."""
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
