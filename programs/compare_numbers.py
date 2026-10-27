from pypdf import PdfReader
import sys, os
sys.path.append(r'C:\Users\User\Desktop\股市\programs')
import generate_daily_investment_reports as gen

print('=== 1. REAL-TIME PYTHON CALCULATION FROM DP.CSV & IP.CSV ===')
fx = 32.5
pf, snap = gen.analyze_portfolio(fx)
print('Total Assets TWD:', f"{snap['total_assets_twd'] / 10000:,.1f} 萬")
print('Securities TWD:', f"{snap['securities_twd'] / 10000:,.1f} 萬")
print('Known Cost TWD:', f"{snap['known_cost_twd'] / 10000:,.1f} 萬")
print('Capital PnL TWD:', f"{snap['cumulative_pnl_twd'] / 10000:,.1f} 萬 ({snap['cumulative_pnl_twd']:,.0f} 元)")
print('Capital Return %:', f"{snap['cumulative_return_pct']:.2f}%")
print('Dividends TWD:', f"{snap['total_div_twd'] / 10000:,.1f} 萬 ({snap['total_div_twd']:,.0f} 元)")
print('PnL with Div TWD:', f"{snap['pnl_with_div_twd'] / 10000:,.1f} 萬 ({snap['pnl_with_div_twd']:,.0f} 元)")
print('Return % with Div:', f"{snap['total_return_with_div_pct']:.2f}%")

print('\n=== 2. EXTRACTED TEXT FROM PDF FILE (個人投資部位分析報告_2026-07-21.pdf) ===')
r = PdfReader(r'C:\Users\User\Desktop\股市\個人投資部位分析報告_2026-07-21.pdf')
for i, page in enumerate(r.pages, 1):
    print(f'--- Page {i} ---')
    lines = page.extract_text().splitlines()
    for line in lines:
        if any(k in line for k in ['資產', '利得', '股息', '損益', '報酬', '萬', '633', '627', '23', '1075', '1098']):
            print(line)
