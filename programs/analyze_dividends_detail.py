import sys, os, pandas as pd, re, json, urllib.request, ssl

POSITION_DIR = r'C:\Users\User\Desktop\股市\投資部位'
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def clean_num(v):
    if v is None or pd.isna(v): return None
    s = str(v).replace(',', '').replace('$', '').replace('%', '').strip()
    try: return float(s)
    except: return None

def fetch_past_year_dividends(symbol):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d&events=div'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    total_div = 0.0
    div_details = []
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            js = json.loads(r.read().decode('utf-8'))
            chart = js.get('chart', {}).get('result', [])[0]
            events = chart.get('events', {}).get('dividends', {})
            for timestamp, div_info in events.items():
                amount = float(div_info.get('amount', 0.0))
                dt = pd.to_datetime(int(timestamp), unit='s').strftime('%Y-%m-%d')
                total_div += amount
                div_details.append((dt, amount))
    except Exception as e:
        pass
    return total_div, div_details

dp_path = os.path.join(POSITION_DIR, 'DP.csv')
dp_rows = []
for line in open(dp_path, 'r', encoding='cp950', errors='replace'):
    line = line.strip()
    if not line or line.startswith('股票名稱'): continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) < 12: continue
    name_full = parts[0]
    m = re.search(r'\(([^)]+)\)', name_full)
    sid = m.group(1) if m else name_full
    name = re.sub(r'\([^)]+\)', '', name_full)
    cost_twd = clean_num(parts[3]) or 0
    old_price = clean_num(parts[5]) or 0
    old_val = clean_num(parts[6]) or 0
    shares = clean_num(parts[2]) or (old_val / old_price if old_price > 0 else 0)
    
    sym = f'{sid}.TW' if sid.isdigit() and len(sid)==4 else f'{sid}.TWO'
    div_per_share, details = fetch_past_year_dividends(sym)
    div_twd = shares * div_per_share
    dp_rows.append({'sid': sid, 'name': name, 'shares': shares, 'cost': cost_twd, 'value': old_val, 'div_per_share': div_per_share, 'div_twd': div_twd, 'details': details})

df_dp = pd.DataFrame(dp_rows)
print('=== 台股部位 (DP.csv) 股息明細 ===')
for _, r in df_dp.iterrows():
    print(f"{r['sid']:6s} {r['name']:12s} | 股數:{r['shares']:>9,.0f} | 近一年每股配息:${r['div_per_share']:>6.2f} | 領到股息: NT${r['div_twd']:>10,.0f} 元 | 歷史配息筆數:{len(r['details'])}")

ip_path = os.path.join(POSITION_DIR, 'IP.csv')
df_ip_raw = pd.read_csv(ip_path, encoding='cp950')
df_ip_raw.columns = [c.strip() for c in df_ip_raw.columns]
ip_rows = []
fx = 32.5
for _, r in df_ip_raw.iterrows():
    name_full = str(r['股票名稱'])
    m = re.search(r'\(([^)]+)\)', name_full)
    sid = m.group(1) if m else name_full
    name = re.sub(r'\([^)]+\)', '', name_full).strip()
    cost_usd = clean_num(r['庫存成本']) or 0
    old_val_usd = clean_num(r['庫存現值']) or 0
    old_price_usd = clean_num(r['現價']) or 0
    shares = clean_num(r.get('庫存股數')) or (old_val_usd / old_price_usd if old_price_usd > 0 else 0)
    
    div_per_share_usd, details = fetch_past_year_dividends(sid)
    div_twd = shares * div_per_share_usd * fx
    ip_rows.append({'sid': sid, 'name': name, 'shares': shares, 'cost': cost_usd*fx, 'value': old_val_usd*fx, 'div_per_share_usd': div_per_share_usd, 'div_twd': div_twd, 'details': details})

df_ip = pd.DataFrame(ip_rows)
print('\n=== 美股部位 (IP.csv) 股息明細 ===')
for _, r in df_ip.iterrows():
    print(f"{r['sid']:6s} {r['name']:12s} | 股數:{r['shares']:>9,.1f} | 近一年每股配息:${r['div_per_share_usd']:>6.2f}USD | 領到股息: NT${r['div_twd']:>10,.0f} 元 | 歷史配息筆數:{len(r['details'])}")

print('\n=== 總體持股結構分析 ===')
total_sec_val = df_dp['value'].sum() + df_ip['value'].sum()
total_sec_cost = df_dp['cost'].sum() + df_ip['cost'].sum()
total_div = df_dp['div_twd'].sum() + df_ip['div_twd'].sum()
print(f"總證券成本: NT$ {total_sec_cost:,.0f} 元 ({total_sec_cost/10000:.1f} 萬元)")
print(f"總證券市值: NT$ {total_sec_val:,.0f} 元 ({total_sec_val/10000:.1f} 萬元)")
print(f"近一年總股息: NT$ {total_div:,.0f} 元 ({total_div/10000:.1f} 萬元)")
print(f"整體證券股息殖利率 (以現值計): {total_div / total_sec_val * 100:.2f}%")
print(f"整體證券股息殖利率 (以成本計): {total_div / total_sec_cost * 100:.2f}%")
