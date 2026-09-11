from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from zoneinfo import ZoneInfo

import pandas as pd
from lightweight_chart import render_chart
import streamlit as st

from market import CATALOG, DEFAULT_SYMBOLS, MAX_SYMBOLS, parse_symbols, load_symbol, compare_prices
from securities import load_names

st.set_page_config(page_title="台股比較室 | Taiwan market lens", page_icon=":material/query_stats:", layout="wide")
st.caption("TAIWAN MARKET LENS  /  台股・ETF 研究工具")
st.title("台股比較室")
st.write("同一起點，看見不同走勢。比較股票與 ETF 的歷史報酬和風險。")

comparison_tab, correlation_tab, indicators_tab, investment_tab, ai_tab, about_tab = st.tabs(["行情比較", "相關性與分散效果", "指標分析", "投資報酬", "AI 深度解讀", "關於與使用說明"], on_change="rerun", key="analysis_tabs")
with about_tab:
    st.markdown(Path(__file__).with_name("about.md").read_text(encoding="utf-8"))
    st.subheader("資料處理流程")
    st.html(Path(__file__).with_name("data_flow.svg").read_text(encoding="utf-8"))
    with st.expander("Mermaid 流程原始碼"):
        st.code("flowchart TD\n A[選股與權重] --> B[Yahoo 日線與快取]\n B --> C[日期與價格驗證]\n C --> D[百分比分析]\n C --> E{有填金額?}\n E -->|是| F[價值與損益]\n F --> G{開啟配息?}\n G -->|是| H[Close 加除息事件]\n H --> I[配息金額與殖利率]", language="mermaid")

with comparison_tab:
    security_names, name_sources_failed = load_names()
    display_names = {**CATALOG, **security_names}


    def label(symbol):
        return f"{symbol.split('.')[0]} {display_names.get(symbol, '名稱暫未取得')}"

    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    if "chosen_named_symbols" not in st.session_state:
        st.session_state.chosen_named_symbols = list(st.session_state.get("chosen_symbols", DEFAULT_SYMBOLS))
    if "default_selection_v2" not in st.session_state:
        st.session_state.chosen_named_symbols = [s for s in st.session_state.chosen_named_symbols if s != "009828.TW"]
        st.session_state.default_selection_v2 = True
    if "symbol_options" not in st.session_state:
        st.session_state.symbol_options = list(CATALOG)
    st.session_state.symbol_options = list(dict.fromkeys(st.session_state.symbol_options + list(display_names)))


    def add_symbols():
        """Commit additions into the same selection widget, never a hidden second list."""
        text = st.session_state.extra_symbols.strip()
        try:
            incoming = parse_symbols(text)
            if not incoming:
                raise ValueError("請先輸入要加入的股票代碼。")
            current = st.session_state.chosen_named_symbols
            # Remember markets for previously resolved manually added symbols.
            incoming = [next((s for s in st.session_state.symbol_options if s.split('.')[0] == code.split('.')[0]), code)
                        if code.split('.')[0] in text.upper().replace('，', ',').replace(',', ' ').split() else code
                        for code in incoming]
            new = [s for s in incoming if s not in current]
            if len(current) + len(new) > MAX_SYMBOLS:
                raise ValueError(f"目前已選 {len(current)}/{MAX_SYMBOLS} 檔，本次要新增 {len(new)} 檔。請先移除標的再加入；原清單未變更。")
            resolved = []
            for s in new:
                if s in st.session_state.symbol_options:
                    resolved.append(s)
                    continue
                # Probe a recent year, independently of the chart date filter.
                explicit = s in text.upper().replace('，', ',').replace(',', ' ').split()
                candidates = [s] if explicit else [s, s.split('.')[0] + '.TWO']
                for candidate in candidates:
                    try:
                        load_symbol(candidate, (pd.Timestamp(today) - pd.DateOffset(years=1)).date(), today)
                        resolved.append(candidate)
                        break
                    except Exception:
                        continue
                else:
                    raise ValueError(f"無法確認 {s.split('.')[0]} 的行情。請確認代碼／上市日期，或使用 .TW、.TWO 指定市場後重試。原清單未變更。")
            resolved = list(dict.fromkeys(resolved))
            st.session_state.symbol_options = list(dict.fromkeys(st.session_state.symbol_options + resolved))
            st.session_state.chosen_named_symbols = list(dict.fromkeys(resolved + current))
            st.session_state.add_notice = ("success", "已加入並置頂：" + "、".join(label(s) for s in resolved)) if resolved else ("info", "這些標的已在上方清單中，未重複加入。")
            st.session_state.extra_symbols = ""
        except ValueError as exc:
            st.session_state.add_notice = ("error", str(exc))
        except Exception:
            st.session_state.add_notice = ("error", "新增暫時失敗，可能是資料服務或網路異常。請稍後重試；原清單未變更。")


    def clear_add_notice():
        st.session_state.pop("add_notice", None)


    with st.sidebar:
        st.subheader(":material/tune: 比較設定")
        from allocation import preset_picker
        preset_picker()
        selected = st.multiselect("股票與 ETF", st.session_state.symbol_options, key="chosen_named_symbols", format_func=label, max_selections=MAX_SYMBOLS, placeholder="搜尋代碼或名稱", on_change=clear_add_notice)
        st.caption(f"已選 {len(selected)}/{MAX_SYMBOLS} 檔 · 尚可新增 {MAX_SYMBOLS - len(selected)} 檔")
        if len(selected) >= MAX_SYMBOLS:
            st.warning(f"已達 {MAX_SYMBOLS} 檔上限，請先移除一檔，再加入新標的。")
        with st.expander("查看完整已選清單", expanded=False):
            for s in selected:
                st.write(f"{label(s)} · {'上櫃' if s.endswith('.TWO') else '上市'}")
            if not selected:
                st.caption("尚未選擇標的。")
        with st.form("add_symbols_form", border=False):
            st.text_input("其他股票代碼", key="extra_symbols", placeholder="例如 00988B, 6510.TWO", help="輸入後點「加入上方清單」（手機不需 Enter）；多檔以逗號分隔。自動辨識上市／上櫃，也可用 .TW、.TWO 指定。")
            st.caption("輸入完成後，點下方按鈕加入；不需按 Enter。")
            st.form_submit_button("加入上方清單", icon=":material/add:", on_click=add_symbols, width="stretch")
        if "add_notice" in st.session_state:
            kind, message = st.session_state.add_notice
            getattr(st, kind)(message)
        st.caption("新增成功會置頂；上方標籤區可捲動，或展開完整清單查看全部標的。")
        if name_sources_failed:
            st.caption("名稱更新暫不可用（" + "、".join(name_sources_failed) + "），目前使用內建名錄；行情查詢不受影響。")
        st.divider()
        period = st.segmented_control("比較區間", ["3月", "6月", "1年", "3年", "5年", "自訂"], default="1年")
        if period == "自訂":
            custom_start = st.date_input("開始日期", value=(pd.Timestamp(today) - pd.DateOffset(years=1)).date(), min_value=date(2000, 1, 1), max_value=today, format="YYYY/MM/DD", key="custom_start_date")
            custom_end = st.date_input("結束日期", value=today, min_value=date(2000, 1, 1), max_value=today, format="YYYY/MM/DD", key="custom_end_date")
            dates = (custom_start, custom_end)
            if custom_start >= custom_end:
                st.warning("結束日期須晚於開始日期，請調整日期。")
        else:
            months = {"3月": 3, "6月": 6, "1年": 12, "3年": 36, "5年": 60}.get(period, 12)
            dates = ((pd.Timestamp(today) - pd.DateOffset(months=months)).date(), today)
        basis = st.selectbox("價格基準", ["還原價格（含配息調整）", "收盤價（未還原）"], help="還原價格採 Yahoo Adj Close，反映其股利與分割調整，不等於實際含稅再投資績效。")
        refresh = st.button("重新取得資料", icon=":material/refresh:", width="stretch")
        st.caption("日線資料 · 快取 1 小時\n\n資料來源：Yahoo Finance / yfinance")

    symbols = list(dict.fromkeys(selected))
    if not symbols:
        st.info("請從左側選擇至少一檔股票或 ETF，開始比較。", icon=":material/add_chart:"); st.stop()
    if len(symbols) > MAX_SYMBOLS:
        st.warning(f"最多比較 {MAX_SYMBOLS} 檔，請減少選擇或手動輸入的代碼。"); st.stop()
    if len(dates) != 2 or dates[0] >= dates[1]:
        st.info("請選擇完整日期區間，且結束日期須晚於開始日期。"); st.stop()
    from allocation import allocation_picker
    with st.sidebar:
        weights, portfolio_name = allocation_picker(symbols, label)
        if "investment_amount_wan" not in st.session_state and st.session_state.get("investment_amount") is not None:
            st.session_state.investment_amount_wan = st.session_state.investment_amount / 10000
        amount_wan = st.number_input("總投入金額（選填／萬元）", min_value=0.0, value=None, step=1.0, format="%.1f", placeholder="例如 10 ＝ 10 萬元", help="單位為新台幣萬元；不填則維持百分比分析。", key="investment_amount_wan")
        amount = None if amount_wan is None else amount_wan * 10000
    start, end = dates
    if refresh:
        for symbol in symbols:
            load_symbol.clear(symbol, start, end)

    histories, failures, fetched = {}, {}, []
    with st.spinner("正在取得歷史行情…"):
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(load_symbol, s, start, end): s for s in symbols}
            for job in as_completed(jobs):
                symbol = jobs[job]
                try:
                    history, stamp = job.result()
                    field = "Adj Close" if basis.startswith("還原") else "Close"
                    if field not in history or history[field].dropna().empty:
                        raise ValueError("缺少所選價格基準資料。")
                    histories[symbol] = history[field]
                    fetched.append(stamp)
                except Exception as exc:
                    failures[symbol] = str(exc)
    if failures:
        st.warning("下列標的無法載入，未納入比較：" + "、".join(label(s) for s in failures))
        with st.expander("資料問題與處理方式"):
            st.write("請確認代碼、市場後綴與上市日期；若資料服務忙碌，稍後按「重新取得資料」。")
            for s, reason in failures.items():
                st.text(f"{s}: {reason[:300]}")
    if not histories:
        st.error("目前無法取得行情。請檢查網路或稍後重新取得資料。"); st.stop()
    prices = pd.concat({s: histories[s] for s in symbols if s in histories}, axis=1)
    try:
        aligned, returns, drawdown, stats = compare_prices(prices)
    except ValueError as exc:
        st.warning(str(exc)); st.stop()

    first, last = aligned.index[0], aligned.index[-1]
    st.caption(f"{first:%Y/%m/%d} — {last:%Y/%m/%d}  ·  {len(aligned):,} 個共同交易日  ·  {len(aligned.columns)} 檔標的  ·  {basis}")
    if first > prices.dropna(how="all").index[0] or last < prices.dropna(how="all").index[-1]:
        valid_prices = prices.where((prices > 0) & (prices < float("inf")))
        available = valid_prices.dropna(how="all")
        reasons = []
        if first > available.index[0]:
            previous = available.index[available.index < first][-1]
            for s in available.columns[available.loc[previous].isna()]:
                begins = available[s].first_valid_index()
                detail = f"資料自 {begins:%Y/%m/%d} 起" if begins == first else f"{previous:%Y/%m/%d} 缺少有效資料"
                reasons.append(f"{label(s)}：{detail}，限制共同起日")
        if last < available.index[-1]:
            following = available.index[available.index > last][0]
            for s in available.columns[available.loc[following].isna()]:
                ends = available[s].last_valid_index()
                detail = f"資料截至 {ends:%Y/%m/%d}" if ends == last else f"{following:%Y/%m/%d} 缺少有效資料"
                reasons.append(f"{label(s)}：{detail}，限制共同迄日")
        st.info(f"已自動縮至共同期間 {first:%Y/%m/%d} — {last:%Y/%m/%d}，所有線從 0.0% 開始。\n\n" + "\n\n".join(reasons))
        st.caption("以上為所選區間內資料來源的有效行情日期，不一定等於掛牌或下市日期。")
    top_symbols = returns.iloc[-1].sort_values(ascending=False, kind="stable").index[:4]
    for card, s in zip(st.columns(len(top_symbols)), top_symbols):
        with card:
            st.metric(label(s), f"{returns[s].iloc[-1]:+.1f}%",
                      delta=f"{first:%Y/%m/%d} — {last:%Y/%m/%d}",
                      delta_color="off", delta_arrow="off", border=True)
    if len(returns.columns) > 4:
        st.caption("上方依區間報酬由高至低顯示前 4 檔；完整標的皆列於下方圖表與報酬風險表。")

    # Stable color identities across selection changes.
    colors = ["#3B9EFF", "#FF922B", "#D0A2FF", "#FFE14A", "#FF5263", "#35E0CE",
              "#C0ED55", "#FF80CB", "#F5F7FA", "#BCA383", "#90A4C2", "#00C853"]
    original_style_order = ["009828.TW"] + DEFAULT_SYMBOLS
    style_order = original_style_order + [s for s in CATALOG if s not in original_style_order]
    style_ids = {s: i for i, s in enumerate(style_order)}
    for s in symbols:
        if s not in style_ids:
            style_ids[s] = len(style_ids)
    # Allocate distinct palette slots within the current comparison while keeping
    # the user's default symbols' colors fixed when other selections are removed.
    used_slots, slots = set(), {}
    for s in returns.columns:
        slot = style_ids[s] % len(colors)
        while slot in used_slots:
            slot = (slot + 1) % len(colors)
        slots[s] = slot
        used_slots.add(slot)
    with st.container(border=True):
        st.subheader("走勢比較")
        view = st.segmented_control("圖表指標", ["累積漲跌幅", "歷史回撤"], default="累積漲跌幅", label_visibility="collapsed", help="累積漲跌幅：相對於共同起始日的漲跌。歷史回撤：相對於區間內截至當天最高價的跌幅，用來觀察從高點下跌的程度。")
        if view == "歷史回撤":
            st.info("歷史回撤＝目前價格距離區間內先前最高價的跌幅。例如從 100 元跌到 90 元，回撤為 −10.0%；回到高點或創新高時為 0.0%。數值越負，代表從高點跌得越深。")
            st.caption("回撤以目前比較區間與所選價格基準計算，並非上市以來的歷史最高價；下方「最大回撤」是這段期間最深的一次回撤。")
        else:
            st.caption("累積漲跌幅：以共同起始日為 0.0%，觀察至各日的漲跌。想知道從高點曾跌多深，可切換「歷史回撤」。")
        chart_data = drawdown if view == "歷史回撤" else returns
        render_chart(chart_data, {s: label(s) for s in chart_data.columns},
                     {s: colors[slots[s]] for s in chart_data.columns}, view)

    st.subheader("報酬與風險")
    st.caption("手機可左右滑動表格查看所有欄位，也可下載 CSV。")
    table = stats.round(1).rename(index=label).reset_index()
    st.dataframe(table, hide_index=True, width="stretch", column_config={c: st.column_config.NumberColumn(c, format="%.1f%%") for c in stats.columns})
    export = returns.rename(columns=label).rename_axis("日期")
    st.download_button("下載比較資料 CSV", export.to_csv(float_format="%.1f").encode("utf-8-sig"), file_name=f"taiwan_returns_{first:%Y%m%d}_{last:%Y%m%d}.csv", mime="text/csv", icon=":material/download:")
    with st.expander("計算方式與資料說明"):
        st.markdown("""
        - **累積漲跌幅**＝（當日價格 ÷ 共同起始日價格 − 1）× 100%。CSV 匯出相同數值。
        - **最大回撤**＝共同交易日價格相對於該區間先前最高價的最大跌幅。
        - **年化報酬**按實際日曆天數換算；不足一年不顯示，避免短期外推。
        - **年化波動**＝各檔每日報酬的樣本標準差 × √252；資料缺漏不補值。
        - 所有曲線只保留各檔都有有效正價格的日期，不以補值模擬停牌交易日。
        - **還原價格**採 Yahoo 的 Adj Close，包含其股利／分割調整；不是扣稅、手續費後的實際投資報酬。未還原收盤價可能有除息或分割跳空。
        - 資料為第三方日線，可能延遲或修訂，當日可能尚未收盤。歷史績效不代表未來。
        """)
    st.caption(f"資料取得時間（台北）：{min(fetched)} · 日線最新共同日期：{last:%Y/%m/%d}")


if correlation_tab.open:
    with correlation_tab:
        from module_compat import load_renderer
        render_analysis = load_renderer("correlation", "render_analysis", "weights")
        render_analysis(prices, label, basis, weights, portfolio_name)

if indicators_tab.open:
    with indicators_tab:
        beta_tab, sharpe_tab = st.tabs(["Beta 分析", "夏普分析"], on_change="rerun", key="indicator_tabs")
        if beta_tab.open:
            with beta_tab:
                from module_compat import load_renderer
                render_beta = load_renderer("beta_analysis", "render_beta", "weights")
                render_beta(prices, label, display_names, start, end, basis, weights, portfolio_name)
        if sharpe_tab.open:
            with sharpe_tab:
                import importlib
                import sharpe_analysis
                if getattr(sharpe_analysis, "UI_VERSION", 0) < 2:
                    importlib.reload(sharpe_analysis)
                sharpe_analysis.render_sharpe(prices, label, basis, weights, portfolio_name)

if investment_tab.open:
    with investment_tab:
        if amount is None or amount <= 0:
            st.subheader("投資報酬")
            st.info("請在側邊欄填入總投入金額（萬元），即可查看資產價值、損益與配息試算。")
        else:
            import importlib
            import investment
            if getattr(investment, "UI_VERSION", 0) < 11:
                importlib.invalidate_caches()
                importlib.reload(investment)
            investment.render_investment(prices, weights, amount, label, basis)

if ai_tab.open:
    with ai_tab:
        from module_compat import load_renderer
        render_ai_page = load_renderer("insights", "render_ai_page", "amount")
        render_ai_page(prices, label, basis, weights, portfolio_name, start, end, amount)
