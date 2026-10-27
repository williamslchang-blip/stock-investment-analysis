import os
import pandas as pd
from datetime import datetime

target_file = r"C:\Users\User\Desktop\股市\programs\generate_daily_investment_reports.py"
with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

target_marker = '    unique_stocks = pd.DataFrame(grouped).sort_values(["last_report_date", "pick_count_20d"], ascending=[False, False])'
end_marker = '        out_df.to_csv(os.path.join(res_dir, "active_selection_tracking_latest.csv"), index=False, encoding="utf-8-sig")'

if target_marker not in content or end_marker not in content:
    print("Markers not found!")
    exit(1)

start_idx = content.find(target_marker)
end_idx = content.find(end_marker) + len(end_marker)

replacement = '''    unique_stocks = pd.DataFrame(grouped).sort_values(["last_report_date", "pick_count_20d"], ascending=[False, False])

    # 最新交易基準日 (由歷史資料最大日期或當前系統日期決定)
    latest_trading_date = str(trading_dates[-1]) if trading_dates else TODAY.isoformat()

    # 讀取既有硬性停損稽核紀錄 (stop_loss_log)，落實「只要建議過"立即停損"，則隔日就不再繼續追蹤」
    res_dir = os.path.join(STOCK_DIR, "results")
    os.makedirs(res_dir, exist_ok=True)
    stop_loss_log_path = os.path.join(res_dir, "active_selection_stop_loss_log.csv")
    stopped_log_dict = {}
    if os.path.exists(stop_loss_log_path):
        try:
            sl_df = pd.read_csv(stop_loss_log_path, encoding="utf-8-sig", dtype=str)
            for _, sl_r in sl_df.iterrows():
                k = (str(sl_r.get("stock_id", "")).strip(), str(sl_r.get("entry_date", "")).strip())
                stopped_log_dict[k] = {
                    "stock_id": str(sl_r.get("stock_id", "")).strip(),
                    "stock_name": str(sl_r.get("stock_name", "")).strip(),
                    "entry_date": str(sl_r.get("entry_date", "")).strip(),
                    "stop_date": str(sl_r.get("stop_date", "")).strip(),
                    "entry_price": clean_num(sl_r.get("entry_price")) or 0.0,
                    "stop_price": clean_num(sl_r.get("stop_price")) or 0.0,
                    "cum_return_pct": clean_num(sl_r.get("cum_return_pct")) or 0.0,
                    "trigger_reason": str(sl_r.get("trigger_reason", "")).strip(),
                    "logged_at": str(sl_r.get("logged_at", "")).strip(),
                }
        except Exception:
            pass

    latest_map = latest.copy()
    latest_map["stock_id"] = latest_map["stock_id"].astype(str)

    rows = []
    for _, old in unique_stocks.iterrows():
        sid = str(old["stock_id"]).strip()
        first_rep_d = str(old["first_report_date"]).strip()
        log_key = (sid, first_rep_d)

        # 核心紀律檢查 1：若過去歷史紀錄中該次進場已曾建議過立即停損，且停損日早於今日，隔日立即終止追蹤！
        if log_key in stopped_log_dict:
            prior_stop_d = str(stopped_log_dict[log_key].get("stop_date", "")).strip()
            if prior_stop_d and prior_stop_d < latest_trading_date:
                continue

        # Calculate trading days held since first_rep_d
        if trading_dates:
            held_days = sum(1 for d in trading_dates if d >= first_rep_d)
        else:
            held_days = 1

        # Find actual entry open price on or after first_rep_d from history, fallback to entry_ref_close
        entry_price = float(old["entry_ref_close"] or 0)
        sub_h = pd.DataFrame()
        if not history.empty:
            sub_h = history[(history["stock_id"].astype(str) == sid) & (history["date"].astype(str) >= first_rep_d)].sort_values("date")
            if not sub_h.empty:
                op_v = clean_num(sub_h.iloc[0].get("open"))
                cl_v = clean_num(sub_h.iloc[0].get("close"))
                if op_v and op_v > 0:
                    entry_price = float(op_v)
                elif cl_v and cl_v > 0:
                    entry_price = float(cl_v)

        entry_pct_chg = clean_num(old["entry_pct_change"]) or 0.0
        stop_loss_threshold = -4.0 if entry_pct_chg >= 3.5 else -6.0

        # 核心紀律檢查 2：回溯自進場日以來的各交易日收盤價，檢查是否在「今日之前的歷史交易日」就已觸發過硬性停損
        historical_stop_date = None
        historical_stop_ret = None
        historical_stop_close = None
        if not sub_h.empty and entry_price > 0:
            for _, day_row in sub_h.iterrows():
                d_str = str(day_row.get("date", "")).strip()
                c_val = clean_num(day_row.get("close"))
                if c_val and c_val > 0:
                    d_ret = ((c_val - entry_price) / entry_price * 100.0)
                    if d_ret <= stop_loss_threshold:
                        historical_stop_date = d_str
                        historical_stop_ret = d_ret
                        historical_stop_close = c_val
                        break

        if historical_stop_date:
            stopped_log_dict[log_key] = {
                "stock_id": sid,
                "stock_name": str(old.get("stock_name", "")).strip(),
                "entry_date": first_rep_d,
                "stop_date": historical_stop_date,
                "entry_price": round(entry_price, 2),
                "stop_price": round(historical_stop_close, 2),
                "cum_return_pct": round(historical_stop_ret, 2),
                "trigger_reason": f"觸發硬性停損線({historical_stop_ret:+.1f}%)，果斷離場",
                "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            if historical_stop_date < latest_trading_date:
                # 歷史上早於最新評估日已觸發立即停損，依使用者紀律「隔日就不再繼續追蹤」，在此剔除！
                continue

        match = latest_map[latest_map["stock_id"] == sid]
        if match.empty:
            rows.append(
                {
                    "stock_id": sid,
                    "stock_name": old.get("stock_name", ""),
                    "entry_date": first_rep_d,
                    "held_days": held_days,
                    "target_days": 15,
                    "PickCount20d": old["pick_count_20d"],
                    "entry_price": round(entry_price, 2),
                    "current_close": 0.0,
                    "entry_str": f"{first_rep_d[5:]}({held_days}日)",
                    "price_str": f"{entry_price:.1f}➔N/A" if entry_price > 0 else "N/A",
                    "cum_return_pct": None,
                    "signals": "N/A",
                    "action": "賣出",
                    "trigger": "最新交易日無報價資料，依紀律離場",
                }
            )
            continue

        r = match.iloc[0]
        close = float(r.get("close", 0) or 0)
        ma120 = float(r.get("ma120", 0) or 0)
        ma20 = float(r.get("ma20", 0) or 0)
        signal_cnt = int(r.get("academic_signal_count", 0) or 0)
        score_val = float(r.get("score", 0) or 0) * 100
        cum_ret = ((close - entry_price) / entry_price * 100) if entry_price > 0 and close > 0 else 0.0

        # Recommended holding target based on stock profile
        is_low_vol = bool(r.get("low_vol", False))
        target_days = 20 if is_low_vol else (5 if old["entry_pct_change"] >= 3.5 else 15)

        action = "續抱"
        trigger = f"持有{held_days}/{target_days}日({cum_ret:+.1f}%)；守穩均線續抱"

        if r.get("volume_down", False):
            action = "賣出"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；觸發放量下跌，依紀律離場"
        elif cum_ret <= -6.0 or (target_days == 5 and cum_ret <= -4.0):
            action = "立即停損"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；觸發硬性停損線，果斷離場"
            # 今日首次觸發立即停損！登錄至停損紀錄，明日起將不再追蹤
            stopped_log_dict[log_key] = {
                "stock_id": sid,
                "stock_name": str(r.get("stock_name", old.get("stock_name", ""))).strip(),
                "entry_date": first_rep_d,
                "stop_date": latest_trading_date,
                "entry_price": round(entry_price, 2),
                "stop_price": round(close, 2),
                "cum_return_pct": round(cum_ret, 2),
                "trigger_reason": f"觸發硬性停損線({cum_ret:+.1f}%)，果斷離場",
                "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        elif close < ma120 and ma120 > 0 and not r.get("relative_strength", False):
            action = "賣出"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；跌破MA120且相對強度轉弱，賣出"
        elif held_days >= target_days:
            action = "到期結算" if cum_ret >= 0 else "到期換股"
            trigger = f"已滿建議持有期{held_days}日(累積{cum_ret:+.1f}%)；執行波段結算換股"
        elif cum_ret >= 10.0 or (target_days == 5 and cum_ret >= 6.0):
            action = "分批停利"
            trigger = f"持有{held_days}日累積達{cum_ret:+.1f}%；達目標區間，分批獲利入袋"
        elif signal_cnt < 4:
            action = "減碼"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；10指標降至{signal_cnt}項，分批減碼"
        elif r.get("overheat", False):
            action = "減碼"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；短線急漲過熱，逢高分批減碼"
        elif close < ma20 and ma20 > 0:
            action = "減碼"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；跌破MA20支撐，減碼防守"

        rows.append(
            {
                "stock_id": sid,
                "stock_name": r.get("stock_name", old.get("stock_name", "")),
                "entry_date": first_rep_d,
                "held_days": held_days,
                "target_days": target_days,
                "PickCount20d": old["pick_count_20d"],
                "entry_price": round(entry_price, 2),
                "current_close": round(close, 2),
                "entry_str": f"{first_rep_d[5:]}({held_days}日)",
                "price_str": f"{entry_price:.1f}➔{close:.1f}",
                "cum_return_pct": round(cum_ret, 2),
                "signals": f"{score_val:.1f}/{signal_cnt}/10",
                "action": action,
                "trigger": trigger,
            }
        )
    out_df = pd.DataFrame(rows)
    try:
        res_dir = os.path.join(STOCK_DIR, "results")
        os.makedirs(res_dir, exist_ok=True)
        out_df.to_csv(os.path.join(res_dir, "active_selection_tracking_latest.csv"), index=False, encoding="utf-8-sig")
        if stopped_log_dict:
            sl_save_df = pd.DataFrame(list(stopped_log_dict.values()))
            sl_save_df.sort_values(["stop_date", "cum_return_pct"], ascending=[False, True], inplace=True)
            sl_save_df.to_csv(os.path.join(res_dir, "active_selection_stop_loss_log.csv"), index=False, encoding="utf-8-sig")'''

new_content = content[:start_idx] + replacement + content[end_idx:]
with open(target_file, "w", encoding="utf-8") as f:
    f.write(new_content)
print("Successfully updated generate_daily_investment_reports.py")
