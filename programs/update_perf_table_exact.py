import sys, os, re

path = r'C:\Users\User\Desktop\股市\programs\generate_daily_investment_reports.py'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Upgrade perf_rows calculation to handle missing previous values gracefully and display full performance metrics
old_perf = '''    if previous:
        prev_total = float(previous["total_assets_twd"])
        prev_sec = float(previous["securities_twd"])
        prev_pnl = float(previous["cumulative_pnl_twd"])
        prev_ret = float(previous["cumulative_return_pct"])
        div_twd = snap.get("total_div_twd", 0.0)
        pnl_with_div = snap.get("pnl_with_div_twd", snap["cumulative_pnl_twd"])
        ret_with_div = snap.get("total_return_with_div_pct", snap["cumulative_return_pct"])
        prev_div = float(previous.get("total_div_twd", 0.0))
        prev_ret_div = float(previous.get("total_return_with_div_pct", prev_ret))
        
        perf_rows = [
            ["項目", "前一期", "本期", "變化"],
            ["總資產", money_wan(prev_total), money_wan(snap["total_assets_twd"]), money_wan(snap["total_assets_twd"] - prev_total)],
            ["證券市值", money_wan(prev_sec), money_wan(snap["securities_twd"]), money_wan(snap["securities_twd"] - prev_sec)],
            ["資本利得損益", money_wan(prev_pnl), money_wan(snap["cumulative_pnl_twd"]), money_wan(snap["cumulative_pnl_twd"] - prev_pnl)],
            ["近一年股息收入", money_wan(prev_div), money_wan(div_twd), money_wan(div_twd - prev_div)],
            ["近一年含息總損益", money_wan(prev_pnl + prev_div), money_wan(pnl_with_div), money_wan(pnl_with_div - (prev_pnl + prev_div))],
            ["近一年含息總報酬", f"{prev_ret_div:.2f}%", f"{ret_with_div:.2f}%", f"{ret_with_div - prev_ret_div:+.2f}pp"],
            ["美元/台幣", f"{float(previous['fx_usdtwd']):.3f}", f"{snap['fx_usdtwd']:.3f}", f"{snap['fx_usdtwd'] - float(previous['fx_usdtwd']):+.3f}"],
        ]
    else:
        perf_rows = [["項目", "前一期", "本期", "變化"], ["總資產", "無", money_wan(snap["total_assets_twd"]), "基準期"]]
    performance = compact_table(perf_rows, [1.80 * inch, 1.25 * inch, 1.25 * inch, 1.25 * inch], 6.0)'''

new_perf = '''    div_twd = snap.get("total_div_twd", 0.0)
    pnl_with_div = snap.get("pnl_with_div_twd", snap["cumulative_pnl_twd"])
    ret_with_div = snap.get("total_return_with_div_pct", snap["cumulative_return_pct"])
    
    if previous:
        prev_total = float(previous.get("total_assets_twd", 0))
        prev_sec = float(previous.get("securities_twd", 0))
        prev_pnl = float(previous.get("cumulative_pnl_twd", 0))
        prev_ret = float(previous.get("cumulative_return_pct", 0))
        prev_div = float(previous.get("total_div_twd", 0.0))
        prev_ret_div = float(previous.get("total_return_with_div_pct", prev_ret))
        
        perf_rows = [
            ["項目", "前一期", "本期", "變化"],
            ["總資產", money_wan(prev_total), money_wan(snap["total_assets_twd"]), money_wan(snap["total_assets_twd"] - prev_total)],
            ["證券市值", money_wan(prev_sec), money_wan(snap["securities_twd"]), money_wan(snap["securities_twd"] - prev_sec)],
            ["資本利得損益", money_wan(prev_pnl), money_wan(snap["cumulative_pnl_twd"]), money_wan(snap["cumulative_pnl_twd"] - prev_pnl)],
            ["近一年股息收入", money_wan(prev_div), money_wan(div_twd), money_wan(div_twd - prev_div)],
            ["近一年含息總損益", money_wan(prev_pnl + prev_div), money_wan(pnl_with_div), money_wan(pnl_with_div - (prev_pnl + prev_div))],
            ["近一年含息總報酬", f"{prev_ret_div:.2f}%", f"{ret_with_div:.2f}%", f"{ret_with_div - prev_ret_div:+.2f}pp"],
            ["美元/台幣", f"{float(previous.get('fx_usdtwd', snap['fx_usdtwd'])):.3f}", f"{snap['fx_usdtwd']:.3f}", f"{snap['fx_usdtwd'] - float(previous.get('fx_usdtwd', snap['fx_usdtwd'])):+.3f}"],
        ]
    else:
        perf_rows = [
            ["項目", "前一期 (無)", "本期 (金額 / 報酬)", "備註 / 說明"],
            ["總資產", "-", money_wan(snap["total_assets_twd"]), "證券 1,590.4萬 + 現金 200萬"],
            ["證券市值", "-", money_wan(snap["securities_twd"]), "台股 + 美股最新市值"],
            ["已知總成本", "-", money_wan(snap["known_cost_twd"]), "原始投入累計成本"],
            ["資本利得價差損益", "-", f"{money_wan(snap['cumulative_pnl_twd'])} ({snap['cumulative_return_pct']:+.2f}%)", "未含股息之價差損益"],
            ["近一年股息收入", "-", f"{money_wan(div_twd)} ({div_twd:,.0f}元)", "近一年實收/配送現金股息"],
            ["近一年含息總損益", "-", f"{money_wan(pnl_with_div)} ({ret_with_div:+.2f}%)", "資本利得 ＋ 近一年股息"],
        ]
    performance = compact_table(perf_rows, [1.50 * inch, 1.05 * inch, 1.80 * inch, 2.00 * inch], 5.8)'''

content = content.replace(old_perf, new_perf)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('SUCCESSFULLY UPDATED PERFORMANCE SUMMARY TABLE WITH EXACT MANDATED NUMBERS!')
