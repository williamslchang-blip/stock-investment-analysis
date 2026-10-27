# 投資報告自動化專案紀錄

## 專案目的

此專案用於每日自動產生投資研究與個人持股檢核報告，整合台股日行情、三大法人、全球市場指數、商品與匯率、個人持股檔，輸出 PDF 報告與晚間追蹤紀錄。

## 專案位置

- 根目錄：`C:\Users\User\Desktop\股市`
- 主產製程式：`programs/generate_daily_investment_reports.py`
- 自動化主控：`programs/daily_investment_automation.py`
- 排程啟動器：`programs/run_daily_investment_automation.ps1`
- 排程安裝腳本：`programs/install_scheduled_tasks.ps1`

## Windows 排程

- `AutomatedInvestment-MorningReport`
  - 預設時間：週一至週五 08:30
  - 模式：`morning`
  - 功能：產生全球投資市場研究報告與個人投資部位分析報告。

- `AutomatedInvestment-EveningReview`
  - 預設時間：週一至週五 20:30
  - 模式：`evening`
  - 功能：收盤後檢查早上選股名單，不因單日結果自動大幅改權重。

## 主要輸入資料

- 個人台股持股：`投資部位/DP.csv`
- 個人海外持股：`投資部位/IP.csv`
- 台股上市日行情與歷史檔：`twse_listed_close_volume_*.csv`、`twse_listed_close_volume_history_53w.csv`
- 三大法人資料：`twse_T86_*.csv`
- 策略參數：`config/strategy_adjustments.json`
- 早報選股快照：`morning_selection_snapshot_YYYY-MM-DD.json`

## 主要輸出

- 全球市場報告：`全球投資市場研究報告_YYYY-MM-DD.pdf`
- 個人持股報告：`個人投資部位分析報告_YYYY-MM-DD.pdf`
- 晚間檢討結果：`results/evening_review/`（含 `.csv`, `.txt`, `.pdf`）與根目錄 `晚間策略複盤報告_YYYY-MM-DD.pdf`
- 執行紀錄：`logs/`
- QA 與渲染檢查檔：`qa/`


## 報告邏輯重點

- 全球報告頁首的市場情緒應反映前一晚全球盤勢，不只看台股前一交易日廣度。
- 隔夜風險判斷納入 NASDAQ、Philadelphia Semiconductor Index、S&P 500、VIX。
- 個人報告中，ETF 一律歸類為核心持股。
- ETF 判斷包含：
  - 台股代號以 `00` 開頭的 ETF/ETN。
  - 常見海外 ETF 或基金名稱/代號，例如 `SPY`、`QQQ`、`VT`、`BND`、`TLT`、`ETF`、`SPDR`、`VANGUARD`、`ISHARES`。
- `2330` 仍列為核心單股。
- 個人報告第二頁包含 8% 年化報酬目標檢核。

## 8% 年化目標檢核假設

此檢核用於配置檢視，不代表保證報酬。

- 現金：約 1%
- 債券 ETF：約 3.5%
- 高股息 ETF：約 6.5%
- 分散型大盤核心 ETF：約 8%
- 半導體 ETF / QQQ：約 10%
- 衛星股：約 9%

若估算未達 8%，目前建議流程為：

1. 保留約 5% 現金。
2. 將其餘閒置現金優先投入分散型核心 ETF，例如 `0050`、`006208`、`SPY`、`VT`。
3. 單一高波動或科技集中標的逐步降至 5-10%。
4. 模型賣出訊號優先於一般權重調節。

## 2026-07-17 重要變更

- 修正全球報告市場情緒邏輯，使其依照前一晚全球盤勢調整。
- 2026-07-17 全球報告依 NASDAQ -1.47%、SOX -4.29%、S&P 500 -0.51%、VIX +6.76%，由偏多修正為弱勢/偏空觀察。
- 個人報告改為 ETF 一律核心持股。
- 個人報告核心比重調整為 64.6%，衛星比重調整為 24.7%。
- 個人報告新增 8% 年化目標檢核。
- 2026-07-17 個人報告估算年化約 7.86%，距離 8.0% 約差 0.14 個百分點。
- 建議保留約 5% 現金後，先投入約 106.5 萬元至分散型核心 ETF。

## 注意事項

- 若 PDF 被 Adobe Acrobat 或其他閱讀器開啟，Windows 可能鎖定檔案，導致重產時無法覆寫。
- 若網路或 Yahoo/TWSE 資料下載失敗，報告可能使用既有快取或顯示資料不足；交付前應用 PDF 文字抽取與 Poppler 渲染頁面檢查。
- `PROJECT_STATUS.md` 與部分舊文件存在編碼亂碼，新的專案紀錄以此檔為準。
