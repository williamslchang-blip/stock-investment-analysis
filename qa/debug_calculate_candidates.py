# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import pandas as pd

ROOT = Path(r'C:\Users\User\Desktop\股市')
sys.path.insert(0, str(ROOT / 'programs'))

import generate_daily_investment_reports as gdir

history = pd.read_csv(ROOT / 'twse_listed_close_volume_history_53w.csv', encoding='utf-8-sig', dtype={'stock_id': str}, low_memory=False)
status = gdir.market_status(history)
print('Market status:', status)

t86, t86_err = gdir.download_t86(pd.to_datetime('2026-10-22').date())
print('t86 records count:', len(t86) if t86 else 0)

latest, candidates = gdir.calculate_candidates(history, status, t86)
print('Latest shape:', latest.shape if latest is not None else None)
print('Candidates shape:', candidates.shape if candidates is not None else None)
if candidates is not None:
    print('Candidates head:')
    print(candidates[['stock_id', 'stock_name', 'score', 'same_month_effect', 'same_month_note']].head(10))
