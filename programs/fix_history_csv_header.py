import os, pandas as pd

STOCK_DIR = r'C:\Users\User\Desktop\股市'
hist_path = os.path.join(STOCK_DIR, "portfolio_performance_history.csv")

if os.path.exists(hist_path):
    lines = open(hist_path, 'r', encoding='utf-8-sig').readlines()
    if lines:
        header = lines[0].strip().split(',')
        new_header = [h.strip() for h in header]
        rows = []
        for line in lines[1:]:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) == 14 and 'total_div_twd' not in new_header:
                # Add default 0.0 values for old 14-field rows
                parts.insert(7, "0.0000") # total_div_twd
                parts.insert(8, parts[5]) # pnl_with_div_twd
                parts.insert(9, parts[6]) # total_return_with_div_pct
                parts.insert(10, "0.0000") # div_yield_pct
            rows.append(parts)
        
        # Standardize header
        standard_cols = [
            "date", "total_assets_twd", "securities_twd", "cash_twd", "known_cost_twd",
            "cumulative_pnl_twd", "cumulative_return_pct", "total_div_twd", "pnl_with_div_twd",
            "total_return_with_div_pct", "div_yield_pct", "tw_value_twd", "us_value_twd",
            "core_pct", "satellite_pct", "bond_pct", "tech_direct_pct", "fx_usdtwd"
        ]
        
        with open(hist_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(",".join(standard_cols) + "\n")
            for r in rows:
                if len(r) == len(standard_cols):
                    f.write(",".join(r) + "\n")
                elif len(r) > 0:
                    # Pad or trim
                    r_std = (r + ["0.0000"] * len(standard_cols))[:len(standard_cols)]
                    f.write(",".join(r_std) + "\n")

print('SUCCESSFULLY RESTANDARDIZED PORTFOLIO PERFORMANCE HISTORY CSV TO 18 FIELDS!')
