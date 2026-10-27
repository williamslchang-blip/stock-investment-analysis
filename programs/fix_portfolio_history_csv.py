import sys, os, pandas as pd, csv

STOCK_DIR = r'C:\Users\User\Desktop\股市'
hist_path = os.path.join(STOCK_DIR, "portfolio_performance_history.csv")

# If portfolio_performance_history.csv exists, remove the row for TODAY so snap with full dividend fields is appended cleanly
if os.path.exists(hist_path):
    try:
        df = pd.read_csv(hist_path)
        print('Original history rows:', len(df))
        df_clean = df[df['date'].astype(str) != '2026-07-21']
        df_clean.to_csv(hist_path, index=False, encoding='utf-8-sig')
        print('Cleaned history rows:', len(df_clean))
    except Exception as e:
        print('Error cleaning history:', e)

print('SUCCESSFULLY CLEANED TODAY RECORD IN PORTFOLIO HISTORY CSV!')
