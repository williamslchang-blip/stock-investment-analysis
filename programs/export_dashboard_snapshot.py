# -*- coding: utf-8 -*-
"""
Export Dashboard Snapshot for GitHub Pages & Offline Use
自動產生供 GitHub Pages (靜態網站) 與離線瀏覽使用的完整決策看板 JSON 快照
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "web"))

from server import MarketDataEngine

def export_snapshot():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在生成 GitHub Pages 儀表板資料快照...")
    engine = MarketDataEngine()
    
    m = engine.get_global_market(force_refresh=True)
    c = engine.get_today_candidates_and_daytrade()
    r = engine.get_exit_radar()
    
    payload = {
        "market": m,
        "candidates": c,
        "exit_radar": r,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "env": "github_pages"
    }
    
    # 輸出至 docs/data 與 web/data
    for target_dir in [ROOT / "docs" / "data", ROOT / "web" / "data"]:
        target_dir.mkdir(parents=True, exist_ok=True)
        out_file = target_dir / "dashboard_data.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 成功產出: {out_file} ({out_file.stat().st_size} bytes)")
        
    print(f"✓ 快照生成完畢！全球指數: {len(m.get('items', []))} 檔, 出場雷達: {r.get('total_tracked', 0)} 檔")

if __name__ == "__main__":
    export_snapshot()
