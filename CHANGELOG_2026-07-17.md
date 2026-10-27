# 2026-07-17 Change Log

## Global market report

- Updated morning market sentiment logic so the top "today market sentiment" and one-line conclusion account for the prior overnight global market session.
- Added risk-first adjustment using NASDAQ, Philadelphia Semiconductor Index, S&P 500, and VIX.
- For the 2026-07-17 global report, the top sentiment was changed from bullish/strong to weak, reflecting NASDAQ -1.47%, SOX -4.29%, S&P 500 -0.51%, and VIX +6.76%.
- Section 5 market ratings were adjusted so Taiwan market, Technology/AI, and Global Risk are not rated bullish when overnight global risk is clearly negative.
- Verified the corrected PDF visually via rendered page PNGs.

## Personal portfolio report

- Changed portfolio classification rule: all ETFs are treated as core holdings.
- ETF detection includes Taiwan tickers beginning with `00` and common US ETF/fund identifiers/names such as `SPY`, `QQQ`, `VT`, `BND`, `TLT`, `ETF`, `SPDR`, `VANGUARD`, and `ISHARES`.
- Rebuilt `個人投資部位分析報告_2026-07-17.pdf`.
- After reclassification, core holdings increased to 64.6% and satellite holdings decreased to 24.7%.
- Added a second-page 8% annualized return target check.
- Current expected annualized return estimate: 7.86%.
- Target gap: +0.14 percentage points versus 8.0%.
- Suggested adjustment: keep about 5% cash, then deploy about TWD 1.065 million of available cash first into diversified core ETFs such as `0050`, `006208`, `SPY`, and `VT`; reduce single high-volatility positions toward 5-10% over time.
- Added explanatory note that return assumptions are for allocation review only, not a guaranteed return.
- Verified the final personal PDF visually via rendered page PNGs.

## Files changed

- `programs/generate_daily_investment_reports.py`
- `個人投資部位分析報告_2026-07-17.pdf`
- `全球投資市場研究報告_2026-07-17_新聞詳細版.pdf`
- `全球投資市場研究報告_2026-07-17_before_market_sentiment_fix.pdf`

## Notes

- `全球投資市場研究報告_2026-07-17.pdf` could not be overwritten during the session because Adobe Acrobat DC was holding a lock on the file.
- The corrected global report exists as `全球投資市場研究報告_2026-07-17_新聞詳細版.pdf`.
