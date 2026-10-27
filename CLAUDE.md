# CLAUDE.md - AI Agent Shared Instructions

本文件供 Claude Code、Codex 與 Antigravity AI 共同遵從，確保專案維護規範一致。

---

## ⚡ 每次執行前強制動作 (Pre-Execution Rule)

**在每次回應使用者或執行任務之前，AI 助手必須明確顯示以下資訊**：
1. **上次執行紀錄** (取自 `PROJECT_STATUS.md` 之「上次執行紀錄」)
2. **本次應執行項目** (取自規劃之「本次應執行項目」)

---

## 🚀 常用命令 (Commands)

```bash
# 1. 執行晨間自動化產報程序（手動觸發）
powershell -ExecutionPolicy Bypass -File "programs/run_daily_investment_automation.ps1" -Mode morning

# 2. 執行晚間策略複盤程序
powershell -ExecutionPolicy Bypass -File "programs/run_daily_investment_automation.ps1" -Mode evening

# 3. 直接使用內建 Python 執行產報主程式
& "C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" programs/generate_daily_investment_reports.py
```

---

## 📜 專案維護與 AI 協作規則

- **PROJECT_STATUS.md**：每次任務執行後必須更新。
- **README.md**：檔案新增、刪除、改名時必須更新。
- **AGENTS.md & CLAUDE.md**：流程、工具、資料源、格式或 Agent 規則改變時更新。
- **資料更新後才產報**：不使用過期數據；先完成 TWSE、Yahoo Finance API 及鉅亨網新聞下載，動態重算持股市值與損益後，再生成 PDF。
- **語言與公式**：全繁體中文；Markdown 使用 LaTeX，Word 使用 Office Math/OMML。
- **模型修改與同步**：若決議調整模型權重，必須出具獨立《策略模型調整與回測報告》；次日產出之《全球投資市場研究報告》Page 2 選股策略說明必須同步更新。
- **動態一句話結論**：全球報告 Page 1 頂部「一句話結論」須動態結合當日鉅亨網與各大財經新聞熱門標題、大盤盤勢與情緒位階操作建議。
- **晚間策略複盤當日開盤至收盤報酬率**：晚間複盤計算當日報酬率一律採用當日開盤價至收盤價報酬率 $\text{Return}_{open\_to\_close} = \frac{\text{Close} - \text{Open}}{\text{Open}} \times 100\%$，並於複盤檔中記錄開盤價與收盤價，避免強勢盤以前一日收盤價計算產生前視偏誤。
- **每季 (約90天/3個月) 投資策略定期覆盤**：每季定期檢查投資策略、因子權重、風控扣分、勝率矩陣與停損門檻；評估是否有需要修改的地方，若需調整須出具獨立《策略模型調整與回測報告》。
- **報告頁數限制**：預設為 2 頁標準 PDF 報告（若觀察標的或資訊量較多時允許彈性延伸為 3 頁）。
- **Codex 執行與 Antigravity 監督**：所有自動化腳本與排程產報一律交由 Codex / Codex primary runtime 執行；Antigravity AI 負責全程監督與驗證（含數據正確性、全球指數、三大法人、部位重算與 PDF 排版視覺），確認 100% 正確後始得完成回報。

