# 專案狀態記錄 (PROJECT_STATUS.md)

## 專案基本資訊

- **專案名稱**：全球股市分析以及個人投資分析
- **專案位置**：C:\Users\User\Desktop\股市
- **使用者**：自己研究用
- **維護語言**：繁體中文
- **當前系統時間**：2026-10-27 (Asia/Taipei)
- **最新狀態**：已成功在 GitHub 上完成 **GitHub Pages 雲端隨身網站** 部署！雲端專屬網址為 [`https://williamslchang-blip.github.io/stock-investment-analysis/`](https://williamslchang-blip.github.io/stock-investment-analysis/)，手機、平板與任何電腦皆可免開機、免本機環境隨時隨地開啟使用。已建立資料快照輸出程式 [`programs/export_dashboard_snapshot.py`](file:///C:/Users/User/Desktop/股市/programs/export_dashboard_snapshot.py) 並串接至晨間自動化排程，實現雲端面板定時同步更新。

---

## 執行紀錄歷史

### 上次執行紀錄 (Last Execution Record)
- **執行時間**：2026-10-27 12:08:00 (Asia/Taipei)
- **執行項目**：
  1. **建置 GitHub Pages 專屬網站架構**：
     - 建立 `docs/` 靜態發布目錄，包含支援雙模態（地端 API / 雲端快照備援）之 [`docs/index.html`](file:///C:/Users/User/Desktop/股市/docs/index.html)。
     - 開發 [`programs/export_dashboard_snapshot.py`](file:///C:/Users/User/Desktop/股市/programs/export_dashboard_snapshot.py)，自動將全球總經行情、當日當沖訊號與 35 檔出場雷達匯出為 `docs/data/dashboard_data.json`。
  2. **啟用 GitHub Pages 託管**：
     - 調用 GitHub Pages API 將 `williamslchang-blip/stock-investment-analysis` 綁定至 `master` 分支的 `/docs` 目錄。
     - 驗證成功上線：`https://williamslchang-blip.github.io/stock-investment-analysis/`（HTTP 200 OK，包含完整資料快照）。
  3. **自動化排程同步掛接**：
     - 於 [`programs/daily_investment_automation.py`](file:///C:/Users/User/Desktop/股市/programs/daily_investment_automation.py) 中注入快照自動產出鉤子，晨間產報完成時同步更新 `docs/data/dashboard_data.json`。
- **執行結果**：
  - GitHub Pages 啟用與部署：**成功 (SUCCESS)**。
  - 雲端網站隨身存取驗證：**成功 (SUCCESS)**（HTTP 200）。
  - 自動化快照排程串接：**成功 (SUCCESS)**。
  - 狀態：**成功 (SUCCESS)**。

---

### 上上次執行紀錄 (Previous Execution Record)
- **執行時間**：2026-10-27 11:37:00 (Asia/Taipei)
- **執行項目**：切換 GitHub 儲存庫為 Public、資安與個人財務隱私防護清洗（移除 84 份個人損益 PDF）。
- **執行結果**：成功 (SUCCESS)。
- **執行結果**：成功 (SUCCESS)。

---

## 已完成核心功能與相關規定總覽

1. **頂部摘要：今日市場情緒燈號 + 一句話總結今日盤勢**
2. **全球市場總覽資料來源與前一日日期鎖定 (Rule 1)**
3. **全球市場總覽右側說明節錄規定 (Rule 1.1)**
4. **商品總經價格 + 產業供應鏈 + 學術 10 指標技術訊號 (Rule 2)**
5. **台股今日重點觀察｜題材、籌碼與風險 (Rule 3)**
6. **資金面金額統計 + 主要外幣 + 綜合 1-5 點操作結論 (Rule 4)**
7. **專業新聞脈絡與 5 大面向評分判讀 (Rule 5)**
8. **第二頁三大法人分別買賣超個股前五名**
9. **今日衛星觀察名單｜當日模型前10＋1年期同月份效應與增量更新機制**
10. **前期建議追蹤與近 20 交易日歷次選股滾動追蹤機制（分批停利、到期結算、硬性停損）**
11. **各大財經媒體熱門子產業與該子產業對應個股推薦（一對一分行排版）**
12. **個人投資部位 (DP.csv & IP.csv) T-1 價格重算 + 近一年股息收入 (NT$23.1萬) 併入總報酬率（保留於日常 PDF 報告）**
13. **個人部位報告佈局與數據校正：PDF 表格完全呈遞 23.1 萬股息與含息總損益 657.0 萬**
14. **選股模型參數治理：過熱門檻下修至 4.5%、持有天數分級、53週歷史自動防斷層自癒機制**
15. **地端即時監控網站與當沖對沖決策系統 (`web/server.py` + `web/index.html` + `啟動在地即時監控儀表板.bat`)**
16. **每季 (約90天/3個月) 投資策略定期覆盤與治理機制：定期檢核學術10指標權重、風控扣分、勝率矩陣與停損門檻，次期應檢核日為 2027-01-25**
17. **GitHub 遠端版本庫同步與資安防護：已掛載至私人儲存庫 williamslchang-blip/stock-investment-analysis，並實施 .gitignore 隔離真實投資部位**
