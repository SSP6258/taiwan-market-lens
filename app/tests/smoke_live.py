"""Manual integration check against live data: python app/tests/smoke_live.py

Not part of CI -- it reaches the network. It exists for the changes unit tests cannot
reach: a real currency conversion, two trading calendars in one portfolio, and every
renderer's own path through the data.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from market import load_symbol, load_frame, compare_prices, currency_of, fx_rates

TODAY = date.today()
YEAR_AGO = (pd.Timestamp(TODAY) - pd.DateOffset(years=1)).date()
MIXED = ["0050.TW", "00984B.TWO", "VT", "00865B.TW"]
checks, failures = [], []


def check(name, condition, detail=""):
    (checks if condition else failures).append(name)
    print(f"  {'PASS' if condition else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def section(title):
    print(f"\n=== {title} ===")


section("1. 取得與幣別")
rates = fx_rates()
check("匯率序列可用", len(rates) > 1000, f"{len(rates)} 筆 {rates.index[0]:%Y-%m-%d} 起")
check("匯率無異常跳動", bool((rates.pct_change().abs().dropna() < 0.10).all()),
      f"最大單日 {rates.pct_change().abs().max()*100:.1f}%")
histories, failed, stamps, notes = load_frame(MIXED, YEAR_AGO, TODAY, "Adj Close")
check("四檔混合幣別皆取得", not failed, str(list(failed)))
check("VT 標示為已換算", "VT" in notes.get("converted", {}))
check("台幣標的未被標示換算", not [s for s in notes.get("converted", {}) if currency_of(s) == "TWD"])

section("2. 行情比較（主頁的計算）")
prices = pd.concat(histories, axis=1)
aligned, returns, drawdown, stats = compare_prices(prices)
check("共同交易日充足", len(aligned) > 200, f"{len(aligned)} 天")
check("所有線自 0% 起", bool(returns.iloc[0].eq(0).all()))
check("報酬數值合理", bool(stats["區間漲跌幅 (%)"].between(-95, 500).all()))
print("    " + "  ".join(f"{s.split('.')[0]} {stats.loc[s,'區間漲跌幅 (%)']:+.1f}%" for s in stats.index))

section("3. 相關性與組合（跨市場行事曆）")
from correlation import analysis_data, portfolio_stats, blend_paths
daily, corr, segment = analysis_data(prices)
check("日報酬筆數足夠", len(daily) >= 20, f"{len(daily)} 筆")
check("連續完整區段未被假期切碎", len(segment) > 200, f"{len(segment)} 天")
weights = pd.Series(0.25, index=prices.columns)
portfolio, volatility, dd = portfolio_stats(segment, weights)
check("組合統計可算", bool(volatility.notna().all() and dd.notna().all()))
blend_return, blend_dd = blend_paths(segment, weights)
check("組合走勢線可畫", len(blend_return) == len(segment) and blend_dd.min() <= 0)

section("4. 夏普")
from sharpe_analysis import sharpe_stats
table = sharpe_stats(segment, weights, 2.0)
check("夏普表含組合列", "組合" in table.index)
check("夏普值有限", bool(table["夏普比率"].replace([float("inf")], float("nan")).notna().any()))

section("5. Beta（美元標的對台幣基準回歸）")
from beta_analysis import fit_beta
benchmark, _ = load_symbol("0050.TW", YEAR_AGO, TODAY)
beta, intercept, r2, pairs = fit_beta(prices["VT"], benchmark["Adj Close"])
check("VT 對 0050 的 Beta 可估", abs(beta) < 5 and len(pairs) >= 20,
      f"Beta {beta:.2f} R² {r2:.2f} 樣本 {len(pairs)}")

section("6. 投資報酬與配息（美元標的的除息換算）")
from investment import load_distributions, cash_result, monthly_distributions
dists = {s: load_distributions(s, YEAR_AGO, TODAY) for s in ("VT", "00984B.TWO")}
check("VT 除息資料取得", not dists["VT"].empty)
vt_div = dists["VT"]["Dividends"]
vt_div = vt_div[vt_div > 0]
check("VT 除息已換算為台幣", bool(len(vt_div) and vt_div.max() > 1),
      f"最大單次 {vt_div.max():.2f} 元（美元原值約 {vt_div.max()/float(rates.iloc[-1]):.2f}）")
first, last = segment.index[0], segment.index[-1]
pair_w = pd.Series({"VT": 0.5, "00984B.TWO": 0.5})
result, events = cash_result(dists, pair_w, 1000e4, first, last)
check("含息試算可算", bool(result["期末市值"].gt(0).all()))
check("每月配息表可建", len(monthly_distributions(events, list(pair_w.index), first, last)) > 0)

section("7. AI 解讀的統計（不呼叫模型）")
from insights import allocation_facts, correlation_pairs, build_payload, conclusions
lines = conclusions(volatility, dd, weights, "等權重組合")
facts = allocation_facts(segment, weights, portfolio, volatility, dd, "等權重組合")
payload = build_payload(lines, correlation_pairs(corr, str), "還原價格", daily, segment, weights, facts)
check("payload 可建且含集中度", "有效持股檔數" in payload and len(payload) > 500)

section("8. 配置比較：全部九個預設")
from strategies import allocation_table, configuration_paths, binding_holding
from allocation import PRESETS
table_all = allocation_table()
check("預設配置共 9 個", len(table_all) == 9, "、".join(table_all))
check("每個配置合計 100%", all(abs(sum(w.values) * 100 - 100) < 0.2 for w in table_all.values()))
all_symbols = sorted({s for w in table_all.values() for s in w.index})
hist2, fail2, _, notes2 = load_frame(all_symbols, YEAR_AGO, TODAY, "Adj Close")
check("所有預設持股皆可取得", not fail2, str(list(fail2)))
prices2 = pd.concat(hist2, axis=1)
paths = configuration_paths(prices2, table_all)
aligned2, _, _, stats2 = compare_prices(paths)
bind = binding_holding(prices2, table_all)
check("九個配置可同時比較", len(aligned2) >= 2,
      f"{aligned2.index[0]:%Y-%m-%d} → {aligned2.index[-1]:%Y-%m-%d}（{len(aligned2)} 天）")
print(f"    卡住起點：{bind[0]} 自 {bind[1]:%Y-%m-%d}　含有它的配置：{bind[2]}")
rest = {k: v for k, v in table_all.items() if k != "退休5"}
aligned3, _, _, stats3 = compare_prices(configuration_paths(prices2, rest))
check("移除退休5 後期間變長", len(aligned3) > len(aligned2),
      f"{len(aligned2)} → {len(aligned3)} 天")
print("    " + "  ".join(f"{k} {stats3.loc[k,'區間漲跌幅 (%)']:+.1f}%" for k in stats3.index))

section("9. 分割偵測仍然有效")
from market import unit_breaks
h52, _ = load_symbol("0052.TW", YEAR_AGO, TODAY)
_, _, _, notes3 = load_frame(["0052.TW"], YEAR_AGO, TODAY, "Adj Close")
found = notes3.get("unit_breaks", {}).get("0052.TW", [])
check("0052 的 1:7 分割仍被校正", bool(found), str([(f"{d:%Y-%m-%d}", v) for d, v in found]))
_, _, _, s52 = compare_prices(pd.concat({"0052.TW": h52["Adj Close"]}, axis=1))
check("0052 區間報酬為正（未被假崩盤污染）", s52.loc["0052.TW", "區間漲跌幅 (%)"] > 0,
      f"{s52.loc['0052.TW','區間漲跌幅 (%)']:+.1f}%")

section("10. 實際頁面：混合幣別下逐一打開每個分頁")
from streamlit.testing.v1 import AppTest
APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
# The chart registers itself when its module is imported, into whichever runtime is
# current. Section 8 imported it already, so drop it and let the AppTest runtime own it.
sys.modules.pop("lightweight_chart", None)
app = AppTest.from_file(APP)
app.session_state["portfolio_presets_initialized"] = True
app.session_state["chosen_named_symbols"] = MIXED
app.session_state["investment_amount_wan"] = 3000.0
app = app.run(timeout=180)
check("主頁（行情比較）可渲染", not app.exception, str(app.exception)[:150])
check("換算揭露有出現", bool([c for c in app.caption if "換算為新臺幣" in c.value]))
for tab in ("配置比較", "投資報酬", "AI 深度解讀", "關於與使用說明"):
    app.session_state["analysis_tabs"] = tab
    app = app.run(timeout=180)
    check(f"分頁「{tab}」可渲染", not app.exception, str(app.exception)[:150])
# AppTest has no way to pick a nested tab, and the existing suite only checks that the
# three exist. Drive the renderers directly instead, on real mixed-currency data: that is
# the same code the sub-tabs run, and it is where a conversion bug would surface.
PREAMBLE = (
    "import pandas as pd\n"
    "from market import load_frame\n"
    f"h, _, _, _ = load_frame({MIXED!r}, pd.Timestamp('{YEAR_AGO}').date(),"
    f" pd.Timestamp('{TODAY}').date(), 'Adj Close')\n"
    "p = pd.concat(h, axis=1)\n"
    "w = pd.Series(0.25, index=p.columns)\n"
)
RENDERERS = {
    "相關性與分散效果": (
        "from correlation import render_analysis\n"
        "render_analysis(p, str, '還原價格', w, '等權重組合')\n"),
    "Beta 分析": (
        "from beta_analysis import render_beta\n"
        "render_beta(p, str, list(p), p.index[0].date(), p.index[-1].date(),"
        " '還原價格', w, '等權重組合')\n"),
    "夏普分析": (
        "from sharpe_analysis import render_sharpe\n"
        "render_sharpe(p, str, '還原價格', w, '等權重組合')\n"),
    "投資報酬（含配息）": (
        "from investment import render_investment\n"
        "render_investment(p, w, 3000e4, str, '還原價格')\n"),
    "AI 深度解讀": (
        "from insights import render_ai_page\n"
        "render_ai_page(p, str, '還原價格', w, '等權重組合',"
        " p.index[0].date(), p.index[-1].date(), 3000e4)\n"),
}
for name, body in RENDERERS.items():
    sys.modules.pop("lightweight_chart", None)
    sub = AppTest.from_string(PREAMBLE + body).run(timeout=180)
    check(f"「{name}」以混合幣別渲染", not sub.exception, str(sub.exception)[:150])
    if name == "Beta 分析" and not sub.exception:
        check("Beta 出現跨時區警語",
              bool([item for item in sub.warning if "不同時區" in item.value]),
              next((item.value[:50] for item in sub.warning), "（無警語）"))

print(f"\n{'='*60}\n通過 {len(checks)} 項，失敗 {len(failures)} 項")
if failures:
    print("失敗項目：" + "、".join(failures))
raise SystemExit(1 if failures else 0)
