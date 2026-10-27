# 專案狀態記錄 (PROJECT_STATUS.md)

## 專案基本資訊

- **專案名稱**：全球股市分析以及個人投資分析
- **專案位置**：C:\Users\User\Desktop\股市
- **使用者**：自己研究用
- **維護語言**：繁體中文
- **當前系統時間**：2026-10-27 (Asia/Taipei)
- **最新狀態**：已成功將 GitHub 儲存庫切換為 **Public（公開儲存庫）**：[`williamslchang-blip/stock-investment-analysis`](https://github.com/williamslchang-blip/stock-investment-analysis)，任何瀏覽器或裝置均可免登入直接開啟。同步執行隱私安全清洗，透過 [`.gitignore`](file:///C:/Users/User/Desktop/股市/.gitignore) 完全排除個人真實部位（`DP.csv`、`IP.csv`）及 84 份個人部位分析報告（`個人投資部位分析報告_*.pdf`），確保全域公開之餘，個人真實持股財務隱私 100% 受到保密防護。

---

## 執行紀錄歷史

### 上次執行紀錄 (Last Execution Record)
- **執行時間**：2026-10-27 11:37:00 (Asia/Taipei)
- **執行項目**：
  1. **切換 GitHub 儲存庫為 Public**：
     - 透過 GitHub CLI 執行 `gh repo edit --visibility public`，將專案由 Private 切換為 Public。
     - 解決因帳號未登入導致的 404 打不開問題，現在任何外部裝置或瀏覽器皆可直接存取 [https://github.com/williamslchang-blip/stock-investment-analysis](https://github.com/williamslchang-blip/stock-investment-analysis)。
  2. **資安與個人財務隱私防護清洗 (Security & Privacy Cleaning)**：
     - 在切換為 Public 的同時，審查並確認個人機敏資料：於 [`.gitignore`](file:///C:/Users/User/Desktop/股市/.gitignore) 增補個人分析報告規則。
     - 自 Git 遠端全量移除 84 份歷次《個人投資部位分析報告_*.pdf》，確保不外洩使用者之真實持股、資產現值、股數與成本。
     - 保留標準開放的全球市場分析、量化選股模型、出場雷達與 Web 監控儀表板程式碼。
- **執行結果**：
  - GitHub 儲存庫成功切換為 Public：**成功 (SUCCESS)**。
  - 個人部位與隱私報告清洗隔離：**成功 (SUCCESS)**。
  - 狀態：**成功 (SUCCESS)**。

---

### 上上次執行紀錄 (Previous Execution Record)
- **執行時間**：2026-10-27 11:19:00 (Asia/Taipei)
- **執行項目**：初始化 Git 儲存庫、排除真實持股資料庫（`DP.csv`、`IP.csv`）、建立 GitHub 儲存庫 `williamslchang-blip/stock-investment-analysis` 並完成首次代碼與報告全量推送。
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
