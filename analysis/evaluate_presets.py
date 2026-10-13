"""Evaluate the buffer-pool presets (退休5–9) four ways, for analysis/PRESET_EVALUATION.md.

1. Real prices: the app's own backtest() over each preset's actual holdings.
2. Proxy replay: the 2006-06 → 2026-08 proxy returns from the 40-year study
   (monthly_returns.csv), so a retirement that opens just before 2008 can be run.
3. Monte Carlo: 12-month block bootstrap of those proxy returns, 30 years, the same
   draws for every preset; raw history and with each equity market's return equalised.
4. Stress: deterministic year-one shocks, then a plain steady state.

The rule is the app's: a fixed 90:10 split, 4% of the growth pool moved every January,
25% of the buffer set as the year's income and drawn a twelfth a month. run_rule() is a
vectorised copy of retirement_strategy.backtest(); check_equivalence() asserts they agree
before anything else is reported.

Run: /root/.cache/app-fire-venv/bin/python analysis/evaluate_presets.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'app'))

from retirement_strategy import (TRANSFER_RATE, WITHDRAW_RATE, backtest,  # noqa: E402
                                 backtest_prices, pool_split)

PRINCIPAL = 30_000_000
SHARE = 0.90
INFLATION = 0.02          # Taiwan CPI has run near 2%; an assumption, stated in the report
YEARS = 30
PATHS = 4000
BLOCK = 12
SEED = 20261012

# Proxy columns of monthly_returns.csv (all NT$ total returns): tw = TAIEX + 3.5% dividend
# proxy, QQQ = QQQ in NT$, world = VT (synthetic before 2008), short = BIL/SHY in NT$.
# 退休5 holds 009826 (world equity), so it shares 退休6's proxy; 退休8 and 退休9 share one.
PROXY = {
    '退休5/6 世界股': {'world': 0.90, 'short': 0.10},
    '退休7 台股': {'tw': 0.90, 'short': 0.10},
    '退休8/9 台股＋那斯達克': {'tw': 0.50, 'QQQ': 0.40, 'short': 0.10},
}
EQUITIES = ('tw', 'QQQ', 'world')


# ---------------------------------------------------------------- the rule, vectorised
def pool_steps(returns, weights):
    """Monthly growth-pool return for paths × months, holdings left to drift (no rebalance).

    returns: {column: array (paths, T)} with month 0 the starting point (return 0).
    The pool is the opening-weighted sum of each holding's own index, as growth_pool() does.
    """
    growth = {c: w for c, w in weights.items() if c != 'short'}
    total = sum(growth.values())
    index = sum(w / total * np.cumprod(1 + returns[c], axis=1) for c, w in growth.items())
    step = np.zeros_like(index)
    step[:, 1:] = index[:, 1:] / index[:, :-1] - 1
    return step


def run_rule(g, b, principal=PRINCIPAL, share=SHARE,
             transfer_rate=TRANSFER_RATE, withdraw_rate=WITHDRAW_RATE):
    """backtest()'s loop over many paths at once. Month 0 is a January; g[:,0] = b[:,0] = 0.

    Returns yearly income (paths, years) and month-end total assets (paths, T).
    """
    paths, months = g.shape
    growth = np.full(paths, principal * share)
    buffer = np.full(paths, principal * (1 - share))
    draw = np.zeros(paths)
    incomes, totals = [], np.empty((paths, months))
    for t in range(months):
        if t % 12 == 0:
            transfer = growth * transfer_rate
            growth -= transfer
            buffer += transfer
            annual = buffer * withdraw_rate
            draw = annual / 12
            incomes.append(annual)
        spent = np.minimum(draw, np.maximum(buffer, 0.0))
        buffer -= spent
        growth *= 1 + g[:, t]
        buffer *= 1 + b[:, t]
        totals[:, t] = growth + buffer
    return np.stack(incomes, axis=1), totals


def check_equivalence(proxy):
    """run_rule() must reproduce backtest() exactly on real data before it is trusted."""
    frame = proxy.loc['2007-01-31':]
    prices = (1 + frame).cumprod()
    weights = PROXY['退休8/9 台股＋那斯達克']
    run = backtest(prices[['tw', 'QQQ']], prices['short'], PRINCIPAL, SHARE,
                   growth_weights={'tw': weights['tw'], 'QQQ': weights['QQQ']})
    returns = {c: frame[c].to_numpy()[None, :].copy() for c in frame}
    for r in returns.values():
        r[:, 0] = 0.0
    income, totals = run_rule(pool_steps(returns, weights), returns['short'])
    expected = run.loc[run['撥款月'], '年生活費'].to_numpy()
    assert np.allclose(income[0], expected, rtol=1e-9), (income[0][:3], expected[:3])
    assert np.allclose(totals[0], run['總資產'].to_numpy(), rtol=1e-9)
    return len(expected)


# ---------------------------------------------------------------- metrics
def drawdown_stats(values):
    """Max drawdown, longest underwater stretch and longest recovery, in months."""
    values = np.asarray(values, dtype=float)
    peak = np.maximum.accumulate(values)
    dd = values / peak - 1
    underwater, longest, run_len = dd < -1e-12, 0, 0
    for flag in underwater:
        run_len = run_len + 1 if flag else 0
        longest = max(longest, run_len)
    trough = int(np.argmin(dd))
    after = np.nonzero(values[trough:] >= peak[trough])[0]
    recovery = int(after[0]) if len(after) else None
    return {'最大回撤': float(dd.min()), '最長水下月數': longest,
            '谷底到收復月數': recovery}


def monthly_risk(index):
    r = pd.Series(index).pct_change().dropna().to_numpy()
    downside = np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * np.sqrt(12)
    return {'年化波動': float(r.std(ddof=1) * np.sqrt(12)), '下檔波動': float(downside)}


def income_stats(income, deflate=True):
    """Per-path income metrics from yearly nominal income (paths, years)."""
    years = income.shape[1]
    real = income / (1 + INFLATION) ** np.arange(years) if deflate else income
    first = income[:, :1]
    change = income[:, 1:] / income[:, :-1] - 1
    return real, first, change


# ---------------------------------------------------------------- 1. real prices
def real_price_runs():
    today = date.today()
    out = {}
    for preset in ('退休5', '退休6', '退休7', '退休8', '退休9'):
        try:
            growth, buffer = backtest_prices(today, preset)
            weights, _ = pool_split(preset)
            run = backtest(growth, buffer, PRINCIPAL, SHARE, growth_weights=weights)
        except Exception as exc:          # 退休5: 009826 listed 2026-07
            out[preset] = {'錯誤': str(exc)[:120]}
            continue
        out[preset] = summarise_run(run, growth, weights)
        if preset == '退休9':
            # The same window as the others too, so 退休9 can stand beside 退休8.
            short = backtest(growth.loc['2019-12-01':], buffer.loc['2019-12-01':],
                             PRINCIPAL, SHARE, growth_weights=weights)
            out['退休9（2020 起）'] = summarise_run(short, growth.loc['2019-12-01':], weights)
    return out


def summarise_run(run, growth, weights):
    paid = run.loc[run['撥款月'], '年生活費']
    years = paid.index.year
    change = paid.pct_change().dropna()
    growth_m = growth.resample('ME').last().loc[run.index[0]:run.index[-1]]
    blended = sum(w * growth_m[s] / growth_m[s].iloc[0] for s, w in weights.items())
    stats = {'期間': f'{run.index[0]:%Y-%m} — {run.index[-1]:%Y-%m}',
             '年數': round((run.index[-1] - run.index[0]).days / 365.25, 1),
             '首年生活費': float(paid.iloc[0]),
             '末年生活費': float(paid.iloc[-1]), '末年': int(years[-1]),
             '最差單年變化': float(change.min()) if len(change) else None,
             '生活費下降年數': int((change < 0).sum()),
             '期末總資產': float(run['總資產'].iloc[-1]),
             '累計生活費': float(run['當月生活費'].sum())}
    stats.update({f'成長池{k}': v for k, v in drawdown_stats(blended.to_numpy()).items()})
    stats.update({f'成長池{k}': v for k, v in monthly_risk(blended.to_numpy()).items()})
    stats.update({f'總資產{k}': v for k, v in drawdown_stats(run['總資產'].to_numpy()).items()})
    return stats


# ---------------------------------------------------------------- 2. proxy replay
def proxy_replay(proxy):
    """Retire each January 2007..2016 on the proxy history; the 2008 start in detail."""
    out = {}
    for name, weights in PROXY.items():
        rows = {}
        for start in range(2007, 2017):
            frame = proxy.loc[f'{start}-01-31':]
            returns = {c: frame[c].to_numpy()[None, :].copy() for c in frame}
            for r in returns.values():
                r[:, 0] = 0.0
            income, totals = run_rule(pool_steps(returns, weights), returns['short'])
            inc = income[0]
            real = inc / (1 + INFLATION) ** np.arange(len(inc))
            low = int(np.argmin(inc))
            back = np.nonzero(inc[low:] >= inc[0])[0]
            rows[start] = {
                '首年生活費': float(inc[0]),
                '最低年生活費比首年': float(inc.min() / inc[0]), '最低在第幾年': low + 1,
                '回到首年水準需幾年': (int(back[0]) if len(back) else None),
                '最差單年變化': float((inc[1:] / inc[:-1] - 1).min()),
                '第10年實質生活費比首年': float(real[9] / inc[0]) if len(real) >= 10 else None,
                '總資產最大回撤': drawdown_stats(totals[0])['最大回撤'],
                '期末總資產': float(totals[0, -1]), '年數': len(inc)}
        out[name] = rows
    return out


# ---------------------------------------------------------------- 3. Monte Carlo
def equalise(proxy, cagr):
    """Shift each equity market's mean log return to `cagr`, keeping its shape."""
    shifted = proxy.copy()
    target = np.log1p(cagr) / 12
    for c in EQUITIES:
        logs = np.log1p(proxy[c])
        shifted[c] = np.expm1(logs - logs.mean() + target)
    return shifted


def bootstrap(proxy, rng):
    months = YEARS * 12 + 1
    starts = rng.integers(0, len(proxy) - BLOCK + 1, size=(PATHS, months // BLOCK + 1))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(PATHS, -1)[:, :months]
    out = {c: proxy[c].to_numpy()[idx] for c in proxy}
    for r in out.values():
        r[:, 0] = 0.0
    return out


def monte_carlo(proxy):
    scenarios = {'原始歷史': proxy, '股市同為 8%': equalise(proxy, 0.08),
                 '股市同為 5%': equalise(proxy, 0.05)}
    out = {}
    for label, data in scenarios.items():
        # Common random numbers: every preset sees the same sequence of blocks.
        draws = bootstrap(data, np.random.default_rng(SEED))
        out[label] = {}
        for name, weights in PROXY.items():
            income, totals = run_rule(pool_steps(draws, weights), draws['short'])
            real, first, change = income_stats(income)
            ratio = real / first
            terminal_real = totals[:, -1] / (1 + INFLATION) ** YEARS
            out[label][name] = {
                '首年生活費': float(first[0, 0]),
                '第10年實質 P10': float(np.percentile(real[:, 9], 10)),
                '第10年實質 P50': float(np.percentile(real[:, 9], 50)),
                '第30年實質 P10': float(np.percentile(real[:, -1], 10)),
                '第30年實質 P50': float(np.percentile(real[:, -1], 50)),
                '曾低於首年實質75%的機率': float((ratio.min(axis=1) < 0.75).mean()),
                '曾低於首年實質50%的機率': float((ratio.min(axis=1) < 0.50).mean()),
                '最差單年變化 P50': float(np.percentile(change.min(axis=1), 50)),
                '最差單年變化 P10': float(np.percentile(change.min(axis=1), 10)),
                '期末實質總資產 P10': float(np.percentile(terminal_real, 10)),
                '期末實質總資產 P50': float(np.percentile(terminal_real, 50)),
            }
    return out


# ---------------------------------------------------------------- 4. stress
STEADY = {'tw': 0.06, 'QQQ': 0.06, 'world': 0.06, 'short': 0.015}
SHOCKS = {
    '全球股災（股市 −40%）': {'tw': -0.40, 'QQQ': -0.40, 'world': -0.40, 'short': 0.015},
    # Taiwan-only crisis: TAIEX halves, NT$ falls 15% (US$ +17.6%), US equities −20% in US$.
    '台海衝擊（台股 −50%、台幣貶 15%）': {'tw': -0.50, 'QQQ': 0.8 * 1.176 - 1,
                                     'world': 0.8 * 1.176 - 1, 'short': 1.03 * 1.176 - 1},
    # NT$ +20% against the dollar, markets flat in their own currency.
    '台幣急升 20%': {'tw': 0.0, 'QQQ': 1 / 1.2 - 1, 'world': 1 / 1.2 - 1,
                  'short': 1.03 / 1.2 - 1},
}


def stress():
    months = YEARS * 12 + 1
    def path(first_year, years_flat=0):
        series = {}
        for c in ('tw', 'QQQ', 'world', 'short'):
            monthly = np.full(months, (1 + STEADY[c]) ** (1 / 12) - 1)
            if first_year is not None:
                monthly[1:13] = (1 + first_year[c]) ** (1 / 12) - 1
            if years_flat and c != 'short':
                monthly[1:1 + 12 * years_flat] = 0.0
            monthly[0] = 0.0
            series[c] = monthly[None, :]
        return series
    cases = {'基準（每年 6%）': path(None)}
    cases.update({k: path(v) for k, v in SHOCKS.items()})
    cases['失落十年（股市 10 年零報酬）'] = path(None, years_flat=10)
    out = {}
    for case, series in cases.items():
        out[case] = {}
        for name, weights in PROXY.items():
            income, totals = run_rule(pool_steps(series, weights), series['short'])
            inc = income[0]
            low = int(np.argmin(inc[:10]))
            back = np.nonzero(inc[low:] >= inc[0])[0]
            out[case][name] = {
                '第2年生活費比首年': float(inc[1] / inc[0]),
                '前10年最低比首年': float(inc[:10].min() / inc[0]),
                '回到首年水準在第幾年': (low + int(back[0]) + 1 if len(back) else None),
                '第10年實質總資產': float(totals[0, 120] / (1 + INFLATION) ** 10),
            }
    return out


def main():
    proxy = pd.read_csv(HERE / 'monthly_returns.csv', parse_dates=['Date'], index_col='Date')
    proxy = proxy[['tw', 'QQQ', 'world', 'short']]
    checked = check_equivalence(proxy)
    print(f'run_rule() == backtest() on {checked} years of proxy data', file=sys.stderr)
    results = {'設定': {'本金': PRINCIPAL, '成長池比例': SHARE, '撥出率': TRANSFER_RATE,
                      '領出率': WITHDRAW_RATE, '通膨假設': INFLATION, '模擬年數': YEARS,
                      '路徑數': PATHS, '區塊月數': BLOCK, '亂數種子': SEED,
                      '代理資料': f'{proxy.index[0]:%Y-%m} — {proxy.index[-1]:%Y-%m}'},
               '真實行情': real_price_runs(),
               '代理回放': proxy_replay(proxy),
               '蒙地卡羅': monte_carlo(proxy),
               '壓力測試': stress()}
    (HERE / 'preset_evaluation.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
