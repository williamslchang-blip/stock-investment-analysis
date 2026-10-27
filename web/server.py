# -*- coding: utf-8 -*-
"""
web/server.py - 地端即時監控與當日選股當沖對沖決策儀表板伺服器
100% 本地原生標準庫，無須額外 pip 安裝相依套件。
"""
import csv
import io
import json
import math
import os
import re
import socket
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 強制標準輸出為 UTF-8
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_DIR = ROOT / "programs"
sys.path.insert(0, str(PROGRAMS_DIR))

ssl_ctx = ssl._create_unverified_context()

def get_url(url, timeout=10):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as r:
            return r.read()
    except Exception as e:
        return None

def fetch_yahoo_quote(symbol):
    """抓取單一標的最新報價資訊（收盤價、前收價、漲跌幅、最高價、最低價、開盤價）"""
    q = urllib.parse.quote(symbol, safe="")
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=5d&interval=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{q}?range=5d&interval=1d",
    ]
    for url in urls:
        raw = get_url(url, timeout=8)
        if not raw:
            continue
        try:
            js = json.loads(raw.decode("utf-8"))
            res = js["chart"]["result"][0]
            meta = res.get("meta", {})
            quote = res["indicators"]["quote"][0]
            closes = [c for c in quote.get("close", []) if c is not None]
            opens = [o for o in quote.get("open", []) if o is not None]
            highs = [h for h in quote.get("high", []) if h is not None]
            lows = [l for l in quote.get("low", []) if l is not None]
            volumes = [v for v in quote.get("volume", []) if v is not None]
            
            cur_price = meta.get("regularMarketPrice")
            if cur_price is None and closes:
                cur_price = closes[-1]
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            if (prev_close is None or prev_close == 0) and len(closes) >= 2:
                prev_close = closes[-2]
            elif prev_close is None:
                prev_close = cur_price
                
            open_p = opens[-1] if opens else cur_price
            high_p = max(highs) if highs else cur_price
            low_p = min(lows) if lows else cur_price
            vol = volumes[-1] if volumes else 0
            
            pct = ((cur_price / prev_close) - 1.0) * 100.0 if prev_close and prev_close > 0 else 0.0
            
            return {
                "symbol": symbol,
                "price": round(float(cur_price), 2),
                "prev_close": round(float(prev_close), 2),
                "open": round(float(open_p), 2),
                "high": round(float(high_p), 2),
                "low": round(float(low_p), 2),
                "change": round(float(cur_price - prev_close), 2),
                "pct_change": round(pct, 2),
                "volume": vol,
                "status": "success",
                "time": datetime.now().strftime("%H:%M:%S")
            }
        except Exception:
            continue
    return None

class MarketDataEngine:
    """即時行情與當沖對沖決策計算引擎"""
    def __init__(self):
        self.cached_market = None
        self.cached_candidates = None
        self.cached_exit_radar = None
        self.cached_portfolio = None
        self.last_update = None
        
    def get_global_market(self, force_refresh=False):
        if self.cached_market and not force_refresh and self.last_update:
            if (datetime.now() - self.last_update).seconds < 60:
                return self.cached_market
                
        # 標的清單
        symbols = [
            ("^TWII", "台灣加權指數", "台股大盤"),
            ("^TWOII", "台灣櫃買指數", "中小型股"),
            ("^DJI", "道瓊工業指數", "美股藍籌"),
            ("^GSPC", "標普500指數", "全球基準"),
            ("^IXIC", "那斯達克指數", "科技巨頭"),
            ("^SOX", "費城半導體", "晶片半導體"),
            ("2330.TW", "台積電", "權值王"),
            ("TSM", "台積電 ADR", "美股溢價"),
            ("^VIX", "恐慌指數 (VIX)", "市場情緒"),
            ("^TNX", "美國10年公債殖利率", "總經無風險利率"),
            ("DX-Y.NYB", "美元指數 (DXY)", "國際匯流動向"),
            ("GC=F", "紐約黃金期貨", "避險資產"),
            ("CL=F", "WTI 輕原油期貨", "大宗通膨"),
        ]
        
        results = []
        for sym, name, note in symbols:
            q = fetch_yahoo_quote(sym)
            if q:
                q["name"] = name
                q["category"] = note
                results.append(q)
            else:
                results.append({
                    "symbol": sym,
                    "name": name,
                    "category": note,
                    "price": 0.0,
                    "pct_change": 0.0,
                    "status": "offline"
                })
                
        # 計算市場情緒分數
        vix_item = next((x for x in results if x["symbol"] == "^VIX"), None)
        sox_item = next((x for x in results if x["symbol"] == "^SOX"), None)
        tw_item = next((x for x in results if x["symbol"] == "^TWII"), None)
        
        vix_val = vix_item["price"] if vix_item and vix_item["price"] > 0 else 18.0
        sox_pct = sox_item["pct_change"] if sox_item else 0.0
        tw_pct = tw_item["pct_change"] if tw_item else 0.0
        
        score = 60
        if vix_val < 15: score += 15
        elif vix_val > 25: score -= 25
        elif vix_val > 20: score -= 10
        
        if sox_pct > 1.5: score += 15
        elif sox_pct < -1.5: score -= 15
        
        if tw_pct > 0.8: score += 10
        elif tw_pct < -0.8: score -= 15
        
        score = max(10, min(95, score))
        
        sentiment = (
            "強勢多頭 🚀 (可積極操作，順勢進攻)" if score >= 75
            else "溫和偏多 📈 (拉回支撐做多，嚴選低基期)" if score >= 55
            else "震盪整理 ⚖️ (區間操作，嚴控持股水位)" if score >= 40
            else "偏弱防禦 🛑 (嚴控停損，提高現金水位)"
        )
        
        suggested_position = (
            "70% ~ 80% (偏多攻擊)" if score >= 75
            else "50% ~ 60% (中性偏多)" if score >= 55
            else "30% ~ 50% (箱型防禦)" if score >= 40
            else "10% ~ 30% (極度保守，保留充裕現金)"
        )
        
        self.cached_market = {
            "items": results,
            "sentiment_score": score,
            "sentiment_text": sentiment,
            "suggested_position": suggested_position,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.last_update = datetime.now()
        return self.cached_market

    def get_today_candidates_and_daytrade(self):
        """讀取晨間選股名單並計算當日當沖 / 當日對沖機會訊號"""
        # 尋找最新 morning_selection_snapshot
        snapshot_files = sorted(ROOT.glob("morning_selection_snapshot_*.json"))
        if not snapshot_files:
            return {"status": "empty", "candidates": []}
            
        latest_file = snapshot_files[-1]
        try:
            payload = json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception:
            return {"status": "error", "candidates": []}
            
        selected = payload.get("selected", [])
        report_date = payload.get("report_date", "")
        
        # 針對每檔候選股抓取即時行情並評估當沖可行性
        candidates_result = []
        for idx, item in enumerate(selected):
            sid = str(item.get("stock_id", ""))
            name = str(item.get("stock_name", ""))
            industry = str(item.get("industry", ""))
            academic_score = float(item.get("score") or 0.0)
            
            # 即時報價
            q = fetch_yahoo_quote(f"{sid}.TW")
            cur_price = q["price"] if q else float(item.get("close") or 0.0)
            open_price = q["open"] if q else cur_price
            prev_close = q["prev_close"] if q else float(item.get("close") or cur_price)
            pct_change = q["pct_change"] if q else float(item.get("pct_change") or 0.0)
            high_price = q["high"] if q else cur_price
            low_price = q["low"] if q else cur_price
            
            # 當沖核心指標計算
            # 1. 開盤位階 (Open Gap)
            open_gap_pct = ((open_price / prev_close) - 1.0) * 100.0 if prev_close > 0 else 0.0
            # 2. 開盤至目前走勢 (Intraday Momentum)
            open_to_cur_pct = ((cur_price / open_price) - 1.0) * 100.0 if open_price > 0 else 0.0
            # 3. 日內振幅
            day_amplitude_pct = ((high_price - low_price) / prev_close) * 100.0 if prev_close > 0 else 0.0
            
            # 當沖可行性與多空決策判斷
            daytrade_signals = []
            daytrade_action = "觀望觀察"
            daytrade_color = "neutral"
            target_profit_price = round(open_price * 1.025, 2)  # 目標 +2.5%
            stop_loss_price = round(min(open_price * 0.985, open_price - 0.5), 2)  # 跌破開盤價或 -1.5%
            
            if open_gap_pct >= 4.5:
                daytrade_signals.append("開盤跳空過熱(>4.5%)，嚴防主力隔日沖倒貨，禁止追多！")
                daytrade_action = "高檔反對沖 / 避開"
                daytrade_color = "danger"
            elif open_to_cur_pct > 0.8 and cur_price > open_price:
                daytrade_signals.append("股價站穩開盤線走高，多方攻擊動能強勁")
                if academic_score >= 0.70:
                    daytrade_signals.append("學術證據分數優異(>0.70)，具備波段與日內共振潛力")
                daytrade_action = "多方當沖進場 (做多)"
                daytrade_color = "success"
            elif open_to_cur_pct < -0.8 or cur_price < open_price:
                daytrade_signals.append("開盤後走弱跌破開盤價，空方壓制")
                daytrade_action = "禁止當沖 / 現股避險"
                daytrade_color = "warning"
            else:
                daytrade_signals.append("在開盤價附近窄幅整理，等待出量突破方向")
                daytrade_action = "觀望等待突破"
                daytrade_color = "neutral"
                
            candidates_result.append({
                "rank": idx + 1,
                "stock_id": sid,
                "stock_name": name,
                "industry": industry,
                "academic_score": round(academic_score, 3),
                "cur_price": cur_price,
                "prev_close": prev_close,
                "open_price": open_price,
                "pct_change": pct_change,
                "open_gap_pct": round(open_gap_pct, 2),
                "open_to_cur_pct": round(open_to_cur_pct, 2),
                "day_amplitude_pct": round(day_amplitude_pct, 2),
                "daytrade_action": daytrade_action,
                "daytrade_color": daytrade_color,
                "daytrade_signals": daytrade_signals,
                "target_profit_price": target_profit_price,
                "stop_loss_price": stop_loss_price,
                "holding_period": item.get("holding_period", "10-15日(穩健)"),
                "holding_guide": item.get("holding_guide", "沿均線續抱")
            })
            
        return {
            "report_date": report_date,
            "snapshot_file": latest_file.name,
            "candidates": candidates_result,
            "market_note": "若大盤處於空頭或弱勢回檔格局，候選檔數可能為 0（執行空手防禦紀律，當沖亦宜偏向防守避險）。"
        }

    def get_exit_radar(self):
        """讀取近 20 日歷次選股名單，落實『只要建議過"立即停損"，則隔日就不再繼續追蹤』並提供即時當下出場決策判定"""
        tracking_file = ROOT / "results" / "active_selection_tracking_latest.csv"
        stop_loss_log_file = ROOT / "results" / "active_selection_stop_loss_log.csv"
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 讀取既有硬性停損紀錄，若停損日早於今日，隔日立即排除不再追蹤
        prior_stopped_stocks = {}
        if stop_loss_log_file.exists():
            try:
                with open(stop_loss_log_file, encoding="utf-8-sig") as f:
                    for sl_r in csv.DictReader(f):
                        sid = str(sl_r.get("stock_id", "")).strip()
                        s_date = str(sl_r.get("stop_date", "")).strip()
                        if sid and s_date:
                            prior_stopped_stocks[sid] = s_date
            except Exception:
                pass

        tracked_items = []
        if tracking_file.exists():
            try:
                with open(tracking_file, encoding="utf-8-sig") as f:
                    tracked_items = list(csv.DictReader(f))
            except Exception:
                tracked_items = []
                
        exit_radar_results = []
        for r in tracked_items:
            sid = str(r.get("stock_id", "")).strip()
            name = str(r.get("stock_name", "")).strip()
            entry_date = str(r.get("entry_date", "")).strip()
            held_days = int(float(r.get("held_days", 0) or 0))
            target_days = int(float(r.get("target_days", 15) or 15))
            entry_price = float(r.get("entry_price", 0) or 0)

            # 核心紀律：若該股在今日之前的歷史交易日已建議過「立即停損」，隔日不再繼續追蹤
            if sid in prior_stopped_stocks:
                s_date = prior_stopped_stocks[sid]
                if s_date < today_str:
                    continue
            
            # 抓取即時盤中價格
            q = fetch_yahoo_quote(f"{sid}.TW")
            cur_price = q["price"] if q else float(r.get("current_close", entry_price) or entry_price)
            pct_change = q["pct_change"] if q else 0.0
            
            # 計算累積報酬
            cum_ret = ((cur_price / entry_price) - 1.0) * 100.0 if entry_price > 0 else 0.0
            
            # 盤中當下出場決定階梯 (Intra-day Exit Decision Engine)
            status_level = "續抱"
            badge_type = "hold"
            decision_msg = f"持有 {held_days}/{target_days} 日({cum_ret:+.1f}%)；守穩均線軌道續抱"
            
            # 1. 硬性停損 (Emergency Stop Loss)
            if cum_ret <= -6.0 or (target_days == 5 and cum_ret <= -4.0):
                status_level = "🚨 立即停損出場"
                badge_type = "danger"
                decision_msg = f"持有 {held_days} 日累積跌達 {cum_ret:+.1f}%；觸發硬性停損線，建議立即市價離場！"
            elif pct_change <= -4.0 and cur_price < entry_price:
                status_level = "⚠️ 盤中重挫警示"
                badge_type = "warning"
                decision_msg = f"當日重挫 {pct_change:+.1f}%；空方倒貨嚴重，若跌破開盤價建議先出場觀望！"
            # 2. 波段達標分批停利 (Take Profit)
            elif cum_ret >= 10.0 or (target_days == 5 and cum_ret >= 6.0):
                status_level = "🎯 達標分批停利"
                badge_type = "success"
                decision_msg = f"持有 {held_days} 日累積獲利達 {cum_ret:+.1f}%；已達目標停利區間，建議先入袋 1/2 部位！"
            # 3. 建議持有天數到期結算 (Horizon Expiry)
            elif held_days >= target_days:
                status_level = "⏰ 到期結算換股"
                badge_type = "info"
                decision_msg = f"已滿建議持有期 {held_days} 日(累積 {cum_ret:+.1f}%)；波段週期結束，執行到期換股輪動。"
            # 4. 破線減碼
            elif r.get("action") == "減碼" or "跌破" in str(r.get("trigger", "")):
                status_level = "⚠️ 破線減碼防守"
                badge_type = "warning"
                decision_msg = f"持有 {held_days} 日({cum_ret:+.1f}%)；" + str(r.get("trigger", "跌破關鍵均線"))
                
            exit_radar_results.append({
                "stock_id": sid,
                "stock_name": name,
                "entry_date": entry_date,
                "held_days": held_days,
                "target_days": target_days,
                "entry_price": round(entry_price, 2),
                "cur_price": round(cur_price, 2),
                "today_pct": round(pct_change, 2),
                "cum_return_pct": round(cum_ret, 2),
                "status_level": status_level,
                "badge_type": badge_type,
                "decision_msg": decision_msg,
                "signals": r.get("signals", "-")
            })
            
        # 依危急度/處理優先級排序（停損 > 停利 > 到期 > 減碼 > 續抱）
        priority_map = {
            "danger": 0,
            "warning": 1,
            "success": 2,
            "info": 3,
            "hold": 4
        }
        exit_radar_results.sort(key=lambda x: (priority_map.get(x["badge_type"], 5), -x["cum_return_pct"]))
        
        return {
            "total_tracked": len(exit_radar_results),
            "danger_count": sum(1 for x in exit_radar_results if x["badge_type"] == "danger"),
            "take_profit_count": sum(1 for x in exit_radar_results if x["badge_type"] == "success"),
            "expiry_count": sum(1 for x in exit_radar_results if x["badge_type"] == "info"),
            "items": exit_radar_results
        }

engine = MarketDataEngine()

class DashboardHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path in ("/", "/index.html"):
            html_file = Path(__file__).parent / "index.html"
            if html_file.exists():
                content = html_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "index.html not found")
            return
            
        elif path == "/api/global_market":
            data = engine.get_global_market()
            self._send_json(data)
            return
            
        elif path == "/api/today_candidates":
            data = engine.get_today_candidates_and_daytrade()
            self._send_json(data)
            return
            
        elif path == "/api/exit_radar":
            data = engine.get_exit_radar()
            self._send_json(data)
            return
            
        elif path == "/api/all":
            # 一次性整合三大核心面板資料 (全球總經、當日選股當沖、歷次選股出場雷達)
            data = {
                "market": engine.get_global_market(),
                "candidates": engine.get_today_candidates_and_daytrade(),
                "exit_radar": engine.get_exit_radar(),
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self._send_json(data)
            return
            
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        if self.path == "/api/refresh":
            # 強制重新刷新
            engine.get_global_market(force_refresh=True)
            data = {
                "status": "success",
                "message": "已成功強制刷新地端與全球即時報價",
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self._send_json(data)
            return
        self.send_error(404, "Endpoint not found")

    def _send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 保持終端精簡日誌
        return

def run_server(port=8888):
    for p in [port, port + 1, 8080, 8501]:
        try:
            server = ThreadingHTTPServer(("0.0.0.0", p), DashboardHandler)
            print(f"🚀 【股市地端即時監控儀表板】已於本機啟動！")
            print(f"🌐 本機網址：http://127.0.0.1:{p} 或 http://localhost:{p}")
            print(f"📱 區網網址 (同Wi-Fi手機可開)：http://192.168.0.82:{p}")
            server.serve_forever()
            break
        except OSError:
            print(f"⚠️ 連接埠 {p} 被占用，嘗試切換至 {p+1}...")
            continue

if __name__ == "__main__":
    run_server()
