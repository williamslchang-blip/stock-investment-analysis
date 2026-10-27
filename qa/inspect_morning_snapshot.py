# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
root = Path(r'C:\Users\User\Desktop\股市')
data = json.loads((root / 'morning_selection_snapshot_2026-10-27.json').read_text(encoding='utf-8'))
print('Report date:', data['report_date'], 'Data date:', data['recommendation_data_date'])
print('Strategy penalties:', data['strategy'].get('penalties'))
print('Strategy thresholds:', data['strategy'].get('thresholds'))
print('Holding policy:', data['strategy'].get('holding_policy'))
print('\nTop candidates count:', len(data['selected']))
for s in data['selected']:
    print(f"Rank {s['rank']}: [{s['stock_id']}] {s['stock_name']:<6} {s['industry']:<8} Score: {s['score']:.4f} | 52高: {s['score_high52']:.2f} | 產強: {s['score_industry_rs']:.2f} | 個RS: {s['score_stock_rs']:.2f} | 週期: {s.get('holding_period')} | 指引: {s.get('holding_guide')}")
