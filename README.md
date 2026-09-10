# 台股比較室

簡潔的繁體中文 Streamlit 儀表板：同圖比較最多 12 檔台灣股票／ETF，支援還原價格、收盤價、共同日期基準、回撤、年化報酬與波動、CSV 匯出。

預設依序：0050 元大台灣50、2330 台積電、2454 聯發科。皆使用上市 `.TW`。

新增股票：在「其他股票代碼」輸入後按「加入上方清單」或 Enter。新增標的會置頂並與多選清單同步，可直接移除。顯示已選數量／12 檔上限，並提供完整清單；超過上限不變更原選擇。00988B 自動辨識為上櫃玉山嚴選非投債；其他清單外代碼會嘗試辨識上市／上櫃，可手動指定後綴。

## 本地啟動（Windows PowerShell，Python 3.13）

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m streamlit run app/streamlit_app.py
```

安裝後直接雙擊 `run.bat`，會開啟瀏覽器與服務視窗。瀏覽 http://localhost:8501 。保留服務視窗，停止服務按 Ctrl+C。重複執行會重用已啟動的 Dashboard；若 8501 被其他服務占用，會自動在 8502–8510 選擇可用埠，實際網址會印在視窗。也可使用 `start.ps1`。

## Streamlit Community Cloud

1. 將 `streamlit_app.py`、`about.md`、`market.py`、`lightweight_chart.py`、整個 `vendor/`、`static/`、`requirements.txt` 與 `.streamlit/config.toml` 推送到自己的 GitHub repository。
2. 在 Streamlit Community Cloud 建立 app，選 repository／branch，入口填 `streamlit_app.py`。
3. Advanced settings 選 Python 3.13，再部署。此版本不需要 API key。

目前僅本地實作，未建立公開部署。
官方部署說明：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## Lightweight Charts 圖表

使用 Streamlit Custom Components v2 與固定版本 Lightweight Charts 5.0.9，已取代 Plotly。圖表程式隨專案保存在 `vendor/`，瀏覽器不需另外向 CDN 下載，也不需要 Node.js 建置。

- 所有標的實線、固定預設配色，共用百分比座標。
- 拖曳平移、滾輪／觸控縮放、重設縮放。
- 十字游標對應日期，圖例即時顯示該日數值；離開圖表還原最新值。
- 點擊圖例切換曲線，可按「顯示全部」還原。互動在瀏覽器端執行，不會重新抓行情。
- 座標與圖例固定小數 1 位；原始計算精度不變。
- 授權與 copyright notice 位於 `vendor/`，畫面保留 TradingView attribution。
- 來源：https://unpkg.com/lightweight-charts@5.0.9/dist/lightweight-charts.standalone.production.js

## 資料與計算

- 中文名稱與市場來自證交所 ISIN 上市／上櫃證券名錄；每 6 小時快取更新，內建 `data/securities.json` 備援。所有選股標籤、圖表圖例、指標卡、表格及 CSV 使用相同名稱。未收錄的標的顯示「名稱暫未取得」。雲端部署請一併提交 `securities.py` 與 `data/securities.json`。

- yfinance / Yahoo Finance 日線；常用標的清單並非完整股票名錄。其他代碼直接輸入，上市 `.TW`、上櫃 `.TWO`。
- 每檔／區間快取 1 小時，最多 256 筆；最多 4 個平行請求，價格與回撤切換不再抓資料。
- 所有標的有效正價格的交集日期，同一起點設為 0%；不補空值。個別抓取失敗會明確標示並排除，全部失敗顯示錯誤，不產生假行情。
- 累積報酬 `(P/P0-1)*100`；回撤 `(P/cummax(P)-1)*100`，使用共同日期取樣。
- 年化報酬使用 365.25／實際日曆天數，區間不足 365 天留空。波動使用各檔原始每日報酬的樣本標準差 × √252，限制在共同起訖期間，缺值不補。
- Adj Close 為來源的股利／分割調整價格，並非實際扣稅再投資；收盤價模式可能受分割影響。
- 資料服務可能限流、延遲、修訂，當日可能未收盤；公開／商業提供資料前需確認 Yahoo 資料授權。
- yfinance API：https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html

## 測試

```powershell
./.venv/Scripts/python.exe -m pip install pytest
./.venv/Scripts/python.exe -m pytest -q
```

離線測試使用明確隔離的合成資料驗證計算與 UI，不會出現在正式應用程式。

本地可使用未納入 Git 的 `local_defaults.json` 指定預設代碼陣列。本機保留原來 10 檔；雲端未提供此檔時預設為 0050、2330、2454。

## 選用 AI 解讀

數據解讀由程式直接計算，不需要 LLM。AI 按鈕需在本地 `.streamlit/secrets.toml` 或雲端 Secrets 設定 `HF_TOKEN` 與 `HF_MODEL`（使用 Hugging Face Inference Providers 支援的完整模型 ID）。不要提交真實金鑰。點擊才傳送統計摘要；每次連線最多快取 10 組結果，切換資料不顯示舊摘要。服務讀取逾時為 30 秒，失敗可重試。部署請包含 `correlation.py` 與 `insights.py`。

Beta 分析由 `beta_analysis.py` 提供，部署時需一併上傳；支援 0050、加權指數與其他基準，詳見 App 說明分頁。

共用配置由 `allocation.py` 提供，部署需包含此檔。侧邊欄起始比重供分散效果及組合 Beta 共用，選股更換時恢復等權重，行情失敗時不自動重配。

## 專案目錄

```text
run.bat / start.ps1       本地啟動入口
requirements.txt         雲端與本地套件
pytest.ini               測試設定
.streamlit/              主題與服務設定
app/                     所有 Python 程式與應用資源
  streamlit_app.py        Streamlit Cloud 入口
  launch.py              本地啟動器
  tests/                 測試
  data/                  中文名錄備援
  vendor/                圖表引擎與授權
  static/                本地服務識別
  about.md / data_flow.svg 說明與流程圖
  local_defaults.json    本機設定，不上傳 Git
```

部署應提交整個 app 目錄（遵守 .gitignore），以及根目錄 requirements.txt、.streamlit/config.toml。根目錄 streamlit_app.py 為相容入口，載入 app/ 內的實際程式；既有 Streamlit Cloud 入口設定保持不變。根目錄執行 pytest 會自動找到 app/tests。

根目錄僅保留輕量 Python 雲端入口，其餘功能程式全部在 app/；本地啟動器仍直接執行 app/streamlit_app.py。
