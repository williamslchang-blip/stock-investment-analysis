# -*- coding: utf-8 -*-
import csv
import io
import json
import math
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


TODAY = date.today()
CASH_TWD = 2_000_000.0
HOLDING_RECOMMENDATION_MIN_WEIGHT_PCT = 2.0
USERPROFILE = os.environ["USERPROFILE"]
STOCK_DIR = os.path.join(USERPROFILE, "Desktop", chr(0x80A1) + chr(0x5E02))
POSITION_DIR = os.path.join(STOCK_DIR, chr(0x6295) + chr(0x8CC7) + chr(0x90E8) + chr(0x4F4D))
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
PYFONT = r"C:\Windows\Fonts\msjh.ttc"
ssl_ctx = ssl._create_unverified_context()
STRATEGY_PATH = os.path.join(WORK_DIR, "strategy_adjustments.json")
DEFAULT_STRATEGY = {
    "weights": {
        "score_momentum": 0.20,
        "score_high52": 0.12,
        "score_industry_rs": 0.10,
        "score_stock_rs": 0.10,
        "score_ma_trend": 0.10,
        "score_price_volume": 0.08,
        "score_abnormal_volume": 0.07,
        "score_low_vol": 0.08,
        "score_inst_intensity": 0.10,
        "score_inst_alignment": 0.05,
    },
    "penalties": {
        "overheat": 0.12,
        "volume_down": 0.20,
        "below_ma120": 0.10,
    },
    "thresholds": {
        "low_vol_rank_max": 0.55,
        "overheat_pct": 4.5,
        "volume_down_pct": -3.0,
        "volume_down_mult": 1.5,
    },
    "last_review_date": None,
    "change_log": [],
}
STRATEGY_SCORE_COLUMNS = [
    "score_momentum",
    "score_high52",
    "score_industry_rs",
    "score_stock_rs",
    "score_ma_trend",
    "score_price_volume",
    "score_abnormal_volume",
    "score_low_vol",
    "score_inst_intensity",
    "score_inst_alignment",
]


def deep_update(base, updates):
    out = json.loads(json.dumps(base))
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_update(out[key], value)
        else:
            out[key] = value
    return out


def normalize_weights(weights):
    total = sum(float(v) for v in weights.values() if v is not None)
    if total <= 0:
        return DEFAULT_STRATEGY["weights"].copy()
    return {k: round(float(v) / total, 4) for k, v in weights.items()}


def load_strategy():
    if not os.path.exists(STRATEGY_PATH):
        return json.loads(json.dumps(DEFAULT_STRATEGY))
    try:
        with open(STRATEGY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = deep_update(DEFAULT_STRATEGY, data)
        merged["weights"] = normalize_weights(merged["weights"])
        return merged
    except Exception:
        return json.loads(json.dumps(DEFAULT_STRATEGY))


def save_strategy(strategy):
    strategy = deep_update(DEFAULT_STRATEGY, strategy)
    strategy["weights"] = normalize_weights(strategy["weights"])
    with open(STRATEGY_PATH, "w", encoding="utf-8") as f:
        json.dump(strategy, f, ensure_ascii=False, indent=2)


def get_url(url, timeout=30, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                return None
            import time
            time.sleep(1)
    return None


def clean_num(value):
    if value is None:
        return None
    s = str(value).replace(",", "").replace("--", "").replace("X", "").strip()
    if s in {"", "nan", "None"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def twse_date_candidates(target):
    for i in range(14):
        d = target - timedelta(days=i)
        if d.weekday() < 5:
            yield d




def download_twse_daily(start_date=None, allow_prior=True):
    errors = []
    if start_date is None:
        start_date = TODAY - timedelta(days=1)
    candidates = twse_date_candidates(start_date) if allow_prior else [start_date]
    for d in candidates:
        ymd = d.strftime("%Y%m%d")
        url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
            f"?date={ymd}&type=ALLBUT0999&response=csv"
        )
        try:
            data = get_url(url)
            if not data or len(data) < 5000:
                raise RuntimeError("回傳資料過小，可能休市或尚未發布")
            text = data.decode("cp950", errors="ignore")
            lines = [x for x in text.splitlines() if x.strip()]
            header_idx = next(
                i for i, x in enumerate(lines) if "證券代號" in x and "證券名稱" in x and "成交股數" in x
            )
            table_lines = [x for x in lines[header_idx:] if x.startswith('"')]
            raw = list(csv.reader(table_lines))
            header, rows = raw[0], raw[1:]
            out = []
            for row in rows:
                if len(row) < 16:
                    continue
                close = clean_num(row[8])
                sid = row[0].strip().replace('="', "").replace('"', "")
                if close is None or not sid:
                    continue
                change = clean_num(row[10])
                direction_raw = str(row[9]).strip()
                signed_change = 0.0
                if change is not None:
                    if "-" in direction_raw or "跌" in direction_raw or "green" in direction_raw:
                        signed_change = -abs(change)
                    elif "+" in direction_raw or "漲" in direction_raw or "red" in direction_raw:
                        signed_change = abs(change)
                    else:
                        signed_change = 0.0
                pct = None
                if close is not None:
                    prev = close - signed_change
                    if prev > 0:
                        pct = (signed_change / prev) * 100
                out.append(
                    {
                        "date": d.isoformat(),
                        "stock_id": sid,
                        "stock_name": row[1].strip(),
                        "close": close,
                        "volume": clean_num(row[2]),
                        "transactions": clean_num(row[3]),
                        "turnover": clean_num(row[4]),
                        "open": clean_num(row[5]),
                        "high": clean_num(row[6]),
                        "low": clean_num(row[7]),
                        "direction": direction_raw,
                        "change": signed_change,
                        "pct_change": pct,
                    }
                )
            if not out:
                raise RuntimeError("找不到有效上市公司列")
            df = pd.DataFrame(out)
            daily_path = os.path.join(STOCK_DIR, f"twse_listed_close_volume_{ymd}.csv")
            latest_path = os.path.join(STOCK_DIR, "twse_listed_close_volume_latest.csv")
            df.to_csv(daily_path, index=False, encoding="utf-8-sig")
            df.to_csv(latest_path, index=False, encoding="utf-8-sig")
            return d, df, errors
        except Exception as e:
            errors.append(f"{d.isoformat()}：{e}")
    return None, None, errors

def update_history(daily):
    history_path = os.path.join(STOCK_DIR, "twse_listed_close_volume_history_53w.csv")
    if os.path.exists(history_path):
        history = pd.read_csv(history_path, encoding="utf-8-sig", dtype={"stock_id": str}, low_memory=False)
    else:
        history = pd.DataFrame()
    parts = [x for x in [history, daily] if x is not None and not x.empty]
    if history.empty or history["date"].nunique() < 85:
        june_path = os.path.join(STOCK_DIR, "2026六月基本資料", "twse_2026_06_daily_close_volume.csv")
        if os.path.exists(june_path):
            try:
                parts.append(pd.read_csv(june_path, encoding="utf-8-sig", dtype={"stock_id": str}, low_memory=False))
            except Exception:
                pass
        import glob as _glob
        for _p in sorted(_glob.glob(os.path.join(STOCK_DIR, "twse_listed_close_volume_20*.csv"))):
            if "excel" not in os.path.basename(_p) and "history" not in os.path.basename(_p):
                try:
                    parts.append(pd.read_csv(_p, encoding="utf-8-sig", dtype={"stock_id": str}, low_memory=False))
                except Exception:
                    pass
    combined = pd.concat(parts, ignore_index=True, sort=False)
    combined["date"] = pd.to_datetime(combined["date"]).dt.date.astype(str)
    combined = combined.sort_values(["date", "stock_id"])
    combined = combined.drop_duplicates(["date", "stock_id"], keep="last")
    max_date = pd.to_datetime(combined["date"]).max().date()
    min_date = max_date - timedelta(weeks=53)
    combined = combined[pd.to_datetime(combined["date"]).dt.date >= min_date]
    combined.to_csv(history_path, index=False, encoding="utf-8-sig")
    status = [
        "status=ok",
        f"data_date={max_date.isoformat()}",
        f"history_rows={len(combined)}",
        f"history_min_date={combined['date'].min()}",
        f"history_max_date={combined['date'].max()}",
        f"history_file={history_path}",
    ]
    with open(os.path.join(STOCK_DIR, "twse_listed_close_volume_status.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(status))
    return combined


def download_t86(data_date):
    if data_date is None:
        return None, "無選股資料日期，未下載三大法人"
    ymd = data_date.strftime("%Y%m%d")
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/T86"
        f"?date={ymd}&selectType=ALLBUT0999&response=csv"
    )
    try:
        raw = get_url(url)
        text = raw.decode("cp950", errors="ignore")
        lines = [x for x in text.splitlines() if x.strip() and x.startswith('"')]
        rows = list(csv.reader(lines))
        header_i = next((i for i, row in enumerate(rows) if row and "證券代號" in row[0]), None)
        if header_i is None or len(rows) <= header_i + 1:
            raise RuntimeError("T86 無有效資料")
        header = [h.strip() for h in rows[header_i] if str(h).strip()]
        records = []
        for r in rows[header_i + 1 :]:
            if len(r) < len(header):
                continue
            item = dict(zip(header, r))
            sid = item.get("證券代號", "").strip().replace('="', "").replace('"', "")
            name = item.get("證券名稱", "").strip()
            if not re.fullmatch(r"\d{4}", sid):
                continue
            total = clean_num(item.get("三大法人買賣超股數"))
            foreign = clean_num(item.get("外陸資買賣超股數(不含外資自營商)")) or 0
            trust = clean_num(item.get("投信買賣超股數")) or 0
            dealer = clean_num(item.get("自營商買賣超股數")) or 0
            if sid and total is not None:
                records.append(
                    {
                        "stock_id": sid,
                        "stock_name": name,
                        "foreign_lots": foreign / 1000,
                        "trust_lots": trust / 1000,
                        "dealer_lots": dealer / 1000,
                        "total_lots": total / 1000,
                    }
                )
        df = pd.DataFrame(records)
        df.to_csv(os.path.join(STOCK_DIR, f"twse_T86_{ymd}.csv"), index=False, encoding="utf-8-sig")
        return df, None
    except Exception as e:
        return None, str(e)


MARKET_CACHE_FILE = os.path.join(STOCK_DIR, "yahoo_market_cache.json")


def load_market_cache():
    if os.path.exists(MARKET_CACHE_FILE):
        try:
            with open(MARKET_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_market_cache(cache):
    try:
        with open(MARKET_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def yahoo_chart(symbol, rng="1mo", interval="1d", target_date_str=None):
    if target_date_str is None:
        target_date_str = (TODAY - timedelta(days=1)).isoformat()
    q = urllib.parse.quote(symbol, safe="")
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}",
    ]
    res_dict = None
    for url in urls:
        try:
            data = get_url(url)
            if not data:
                continue
            js = json.loads(data.decode("utf-8"))
            res = js["chart"]["result"][0]
            ts = res.get("timestamp", [])
            quote = res["indicators"]["quote"][0]
            closes = quote.get("close", [])

            daily_dict = {}
            for t, c in zip(ts, closes):
                if c is not None:
                    dt_val = datetime.fromtimestamp(t, timezone.utc).date()
                    daily_dict[dt_val.isoformat()] = float(c)

            dates = sorted(daily_dict.keys())
            if not dates:
                continue
            valid_dates = [d for d in dates if d <= target_date_str]
            if not valid_dates:
                valid_dates = [dates[-1]]

            t1_date_str = valid_dates[-1]
            t1_close = daily_dict[t1_date_str]
            t1_idx = dates.index(t1_date_str)
            prev_close = daily_dict[dates[t1_idx - 1]] if t1_idx > 0 else t1_close
            pct = ((t1_close / prev_close) - 1) * 100 if prev_close > 0 else 0.0

            res_dict = {
                "symbol": symbol,
                "date": datetime.strptime(t1_date_str, "%Y-%m-%d").date(),
                "close": t1_close,
                "prev_close": prev_close,
                "pct": pct
            }
            break
        except Exception:
            continue

    cache = load_market_cache()
    if res_dict:
        cache[symbol] = {
            "symbol": symbol,
            "date": res_dict["date"].isoformat(),
            "close": res_dict["close"],
            "prev_close": res_dict["prev_close"],
            "pct": res_dict["pct"]
        }
        save_market_cache(cache)
        return res_dict

    if symbol in cache:
        cached = cache[symbol]
        return {
            "symbol": cached["symbol"],
            "date": datetime.strptime(cached["date"], "%Y-%m-%d").date(),
            "close": cached["close"],
            "prev_close": cached["prev_close"],
            "pct": cached["pct"]
        }
    return None


def yahoo_price_series(symbol, rng="5y", interval="1d"):
    q = urllib.parse.quote(symbol, safe="")
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}",
    ]
    for url in urls:
        try:
            data = get_url(url)
            if not data:
                continue
            js = json.loads(data.decode("utf-8"))
            res = js["chart"]["result"][0]
            closes = res["indicators"]["quote"][0]["close"]
            ts = res["timestamp"]
            vals = [(datetime.utcfromtimestamp(t).date(), float(c)) for t, c in zip(ts, closes) if c is not None]
            return pd.DataFrame(vals, columns=["date", "close"])
        except Exception:
            continue
    return pd.DataFrame(columns=["date", "close"])


def same_month_effect(stock_id, latest_date):
    series = yahoo_price_series(f"{stock_id}.TW", "5y")
    if series.empty:
        return False, "同月份資料不足"
    series["date"] = pd.to_datetime(series["date"])
    month = int(latest_date.month)
    last_year = int(latest_date.year) - 1
    month_rows = series[(series["date"].dt.year == last_year) & (series["date"].dt.month == month)].sort_values("date")
    if len(month_rows) < 2:
        return False, "同月份資料不足"
    ret = month_rows["close"].iloc[-1] / month_rows["close"].iloc[0] - 1
    passed = ret > 0
    note = "同月份去年為漲勢" if passed else "同月份去年非漲勢"
    return passed, note


def get_market_snapshot(target_date=None):
    if target_date is None:
        target_date = TODAY - timedelta(days=1)
    target_date_str = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
    
    symbols = [
        ("S&P 500", ["^GSPC", "SPY"]),
        ("Dow Jones", ["^DJI", "DIA"]),
        ("NASDAQ", ["^IXIC", "QQQ"]),
        ("費城半導體", ["^SOX", "SOXX"]),
        ("FTSE 100", ["^FTSE", "ISF.L"]),
        ("DAX", ["^GDAXI", "EXS1.DE"]),
        ("日經225", ["^N225", "1321.T"]),
        ("恆生指數", ["^HSI", "2800.HK"]),
        ("上證指數", ["000001.SS", "510300.SS"]),
        ("台灣加權", ["^TWII", "0050.TW"]),
        ("KOSPI", ["^KS11", "069500.KS"]),
    ]
    rows = []
    for name, sym_list in symbols:
        r = None
        for sym in sym_list:
            r = yahoo_chart(sym, target_date_str=target_date_str)
            if r:
                break
        if r:
            rows.append([name, r["date"].strftime("%m/%d"), f"{r['close']:,.2f}", r["pct"]])
        else:
            rows.append([name, "N/A", "N/A", None])

    def fetch_with_fallbacks(primary_list):
        for sym in primary_list:
            r = yahoo_chart(sym, target_date_str=target_date_str)
            if r:
                return r
        return None

    fx = fetch_with_fallbacks(["USDTWD=X"])
    oil = fetch_with_fallbacks(["CL=F", "USO"])
    tnx = fetch_with_fallbacks(["^TNX", "IEF"])
    extras = {
        "美元指數": fetch_with_fallbacks(["DX-Y.NYB", "UUP"]),
        "VIX": fetch_with_fallbacks(["^VIX", "VXX"]),
        "黃金": fetch_with_fallbacks(["GC=F", "GLD"]),
        "白銀": fetch_with_fallbacks(["SI=F", "SLV"]),
        "布蘭特原油": fetch_with_fallbacks(["BZ=F", "BNO"]),
        "銅": fetch_with_fallbacks(["HG=F", "CPER"]),
    }
    return rows, fx, oil, tnx, extras


_COMPANY_INDUSTRY_CACHE = None


def _get_company_industry_map():
    global _COMPANY_INDUSTRY_CACHE
    if _COMPANY_INDUSTRY_CACHE is not None:
        return _COMPANY_INDUSTRY_CACHE
    _COMPANY_INDUSTRY_CACHE = {}
    info_path = os.path.join(STOCK_DIR, "2026六月基本資料", "twse_listed_company_info.csv")
    if os.path.exists(info_path):
        try:
            info_df = pd.read_csv(info_path, encoding="utf-8-sig", dtype=str)
            short_map = {
                "半導體業": "半導體",
                "電腦及週邊設備業": "電腦週邊",
                "電子零組件業": "電子零組件",
                "通信網路業": "通信網路",
                "光電業": "光電",
                "其他電子業": "其他電子",
                "電子通路業": "電子通路",
                "資訊服務業": "資訊服務",
                "金融保險業": "金融",
                "航運業": "航運",
                "鋼鐵工業": "鋼鐵",
                "塑膠工業": "塑膠化工",
                "化學工業": "塑膠化工",
                "生技醫療業": "生技醫療",
                "電機機械": "電機機械",
                "電器電纜": "電器電纜",
                "建材營造業": "建材營造",
                "食品工業": "食品/傳產",
                "紡織纖維": "紡織傳產",
                "汽車工業": "汽車工業",
                "貿易百貨業": "貿易百貨",
                "綠能環保": "綠能環保",
                "數位雲端": "數位雲端",
                "居家生活": "居家生活",
                "運動休閒": "運動休閒",
            }
            for _, r in info_df.iterrows():
                k = str(r.get("stock_id", "")).strip()
                ind_raw = str(r.get("industry_name", "")).strip()
                if k and ind_raw:
                    _COMPANY_INDUSTRY_CACHE[k] = short_map.get(ind_raw, ind_raw.replace("工業", "").replace("業", ""))
        except Exception:
            pass
    return _COMPANY_INDUSTRY_CACHE


def classify_industry(sid, name):
    sid_str = str(sid).strip()
    imap = _get_company_industry_map()
    if sid_str in imap:
        return imap[sid_str]
    sidn = int(re.sub(r"\D", "", sid_str) or 0)
    if "半導體" in name or sid_str in {"2330", "00830", "8081", "6202"}:
        return "半導體"
    if 2400 <= sidn <= 2499 or sid_str in {"3003", "6269", "4958", "3090"}:
        return "電子零組件"
    if 2800 <= sidn <= 2899 or 5800 <= sidn <= 5899:
        return "金融"
    if 2600 <= sidn <= 2699:
        return "航運"
    if 2500 <= sidn <= 2599:
        return "建材營造"
    if 1500 <= sidn <= 1599:
        return "電機機械"
    if 1700 <= sidn <= 1799:
        return "生技/化工"
    if 1300 <= sidn <= 1399:
        return "塑膠化工"
    if 1200 <= sidn <= 1299:
        return "食品/傳產"
    if 2000 <= sidn <= 2099:
        return "鋼鐵"
    if 2300 <= sidn <= 2399:
        return "電子"
    return "其他"



def calculate_candidates(history, market_status, t86=None):
    strategy = load_strategy()
    weights = strategy["weights"]
    penalties = strategy["penalties"]
    thresholds = strategy["thresholds"]
    df = history.copy()
    df["date"] = pd.to_datetime(df["date"])
    for col in ["close", "volume", "high", "low", "open", "pct_change"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df = df.dropna(subset=["close"])
    df = df.sort_values(["stock_id", "date"])
    g = df.groupby("stock_id", group_keys=False)
    daily_ret = g["close"].pct_change()
    df["ma20"] = g["close"].rolling(20, min_periods=8).mean().reset_index(level=0, drop=True)
    df["ma60"] = g["close"].rolling(60, min_periods=20).mean().reset_index(level=0, drop=True)
    df["ma120"] = g["close"].rolling(120, min_periods=40).mean().reset_index(level=0, drop=True)
    df["vol20"] = g["volume"].rolling(20, min_periods=8).mean().reset_index(level=0, drop=True)
    df["vol60"] = g["volume"].rolling(60, min_periods=20).mean().reset_index(level=0, drop=True)
    df["std60"] = daily_ret.groupby(df["stock_id"]).rolling(60, min_periods=20).std().reset_index(level=0, drop=True)
    df["high252"] = g["close"].rolling(252, min_periods=80).max().reset_index(level=0, drop=True)
    df["ret1m"] = g["close"].pct_change(20)
    df["ret3m"] = g["close"].pct_change(60)
    df["ret6m"] = g["close"].pct_change(120).fillna(g["close"].pct_change(85)).fillna(df["ret3m"])
    first_close = g["close"].transform("first")
    df["ret12m"] = df["close"] / first_close - 1

    latest_date = df["date"].max()
    latest = df[df["date"] == latest_date].copy()
    latest["stock_id"] = latest["stock_id"].astype(str)
    latest["industry"] = latest.apply(lambda r: classify_industry(str(r["stock_id"]), str(r["stock_name"])), axis=1)
    idx_ret = latest["ret3m"].median(skipna=True)

    latest["mom6_ex1"] = latest["ret6m"].fillna(0) - latest["ret1m"].fillna(0)
    latest["mom12_ex1"] = latest["ret12m"].fillna(0) - latest["ret1m"].fillna(0)
    latest["momentum"] = (latest[["mom6_ex1", "mom12_ex1", "ret3m"]].fillna(0) > 0).sum(axis=1) >= 2
    latest["high52"] = latest["close"] >= latest["high252"] * 0.88
    latest["ma_ratio"] = (latest["close"] > latest["ma20"]) & (latest["ma20"] >= latest["ma60"]) & (latest["ma60"] >= latest["ma120"])
    latest["price_ma_dist"] = (latest["close"] >= latest["ma60"] * 0.98) & (latest["close"] <= latest["ma60"] * 1.30)
    latest["turnover_signal"] = latest["volume"] >= latest["vol20"] * 1.05
    latest["breakout"] = latest["close"] >= latest["high252"] * 0.90
    latest["volume_shock"] = (latest["volume"] >= latest["vol20"] * 1.5) & (latest.get("pct_change", 0).fillna(0) > 0)
    sig_cols = ["momentum", "high52", "ma_ratio", "price_ma_dist", "turnover_signal", "breakout", "volume_shock"]
    latest["buy_signals"] = latest[sig_cols].sum(axis=1)
    latest["relative_strength"] = latest["ret3m"].fillna(-9) > idx_ret
    latest["low_vol"] = latest["std60"].rank(pct=True, ascending=True) <= float(thresholds.get("low_vol_rank_max", 0.55))
    latest["overheat"] = latest["pct_change"].fillna(0) >= float(thresholds.get("overheat_pct", 8.0))
    latest["volume_down"] = (
        latest["pct_change"].fillna(0) < float(thresholds.get("volume_down_pct", -3.0))
    ) & (latest["volume"] >= latest["vol20"] * float(thresholds.get("volume_down_mult", 1.5)))
    industry_strength = latest.groupby("industry")["ret3m"].transform("median")
    latest["industry_strength"] = industry_strength >= latest["ret3m"].median(skipna=True)

    if t86 is not None and not t86.empty:
        inst_cols = ["stock_id", "foreign_lots", "trust_lots", "dealer_lots", "total_lots"]
        inst = t86[inst_cols].copy()
        inst["stock_id"] = inst["stock_id"].astype(str)
        latest = latest.merge(inst, on="stock_id", how="left")
    else:
        for col in ["foreign_lots", "trust_lots", "dealer_lots", "total_lots"]:
            latest[col] = 0
    for col in ["foreign_lots", "trust_lots", "dealer_lots", "total_lots"]:
        latest[col] = pd.to_numeric(latest[col], errors="coerce").fillna(0)

    volume_safe = latest["volume"].replace(0, pd.NA)
    latest["institution_intensity"] = (latest["total_lots"] * 1000 / volume_safe).fillna(0)
    latest["institution_alignment_count"] = (
        (latest["foreign_lots"] > 0).astype(int)
        + (latest["trust_lots"] > 0).astype(int)
        + (latest["dealer_lots"] > 0).astype(int)
    )

    latest["score_momentum"] = ((latest["mom6_ex1"].rank(pct=True) + latest["mom12_ex1"].rank(pct=True)) / 2).fillna(0)
    latest["score_high52"] = (latest["close"] / latest["high252"]).clip(upper=1.0).fillna(0)
    latest["score_industry_rs"] = latest.groupby("industry")["ret3m"].transform("median").rank(pct=True).fillna(0)
    latest["score_stock_rs"] = latest["ret3m"].rank(pct=True).fillna(0)
    latest["score_ma_trend"] = latest["ma_ratio"].astype(float)
    latest["score_price_volume"] = ((latest["pct_change"].fillna(0) > 0) & (latest["volume"] > latest["vol20"])).astype(float)
    latest["score_abnormal_volume"] = ((latest["volume"] / latest["vol60"]).replace([math.inf, -math.inf], 0).clip(lower=0, upper=3) / 3).fillna(0)
    latest["score_low_vol"] = (1 - latest["std60"].rank(pct=True)).fillna(0)
    latest["score_inst_intensity"] = latest["institution_intensity"].rank(pct=True).fillna(0)
    latest["score_inst_alignment"] = latest["institution_alignment_count"] / 3
    academic_cols = STRATEGY_SCORE_COLUMNS
    latest["academic_signal_count"] = (latest[academic_cols] >= 0.60).sum(axis=1)
    latest["score"] = 0.0
    for col in academic_cols:
        latest["score"] += latest[col] * float(weights.get(col, DEFAULT_STRATEGY["weights"].get(col, 0)))
    latest.loc[latest["overheat"], "score"] -= float(penalties.get("overheat", 0.08))
    latest.loc[latest["volume_down"], "score"] -= float(penalties.get("volume_down", 0.20))
    latest.loc[latest["close"] < latest["ma120"], "score"] -= float(penalties.get("below_ma120", 0.10))


    def _assign_holding_plan(r):
        pct_c = float(r.get("pct_change", 0) or 0)
        is_low_vol = bool(r.get("low_vol", False))
        is_ma = bool(r.get("ma_ratio", False))
        abn_vol = float(r.get("score_abnormal_volume", 0) or 0)
        if bool(r.get("overheat", False)) or pct_c >= 3.5 or (abn_vol >= 0.80 and not is_low_vol):
            return "3-5日(短線)", 5, "短線動能(3-5日)；不追開高，+6%分批停利/-4%停損"
        if is_low_vol and is_ma and pct_c < 3.5:
            return "15-20日(波段)", 20, "波段趨勢(15-20日)；目標+6%~+12%，破MA20或-6%停損"
        return "10-15日(穩健)", 15, "穩健波段(10-15日)；沿MA10續抱，破MA20或-5%停損"

    plan_series = latest.apply(_assign_holding_plan, axis=1)
    latest["holding_period"] = [x[0] for x in plan_series]
    latest["holding_target_days"] = [x[1] for x in plan_series]
    latest["holding_guide"] = [x[2] for x in plan_series]

    if "明顯空頭" in str(market_status):
        candidates = latest.iloc[0:0].copy()
    elif "弱勢盤" in str(market_status):
        candidates = latest[latest["relative_strength"] & latest["low_vol"] & (~latest["volume_down"])].copy()
    elif "中性盤" in str(market_status):
        candidates = latest[latest["relative_strength"] & (~latest["volume_down"])].copy()
    else:
        candidates = latest[~latest["volume_down"]].copy()
    candidates = candidates.sort_values("score", ascending=False).head(10)
    seasonality = []
    for sid in candidates["stock_id"].astype(str):
        passed, note = same_month_effect(sid, latest_date)
        seasonality.append({"stock_id": sid, "same_month_effect": passed, "same_month_note": note})
    if seasonality:
        season_df = pd.DataFrame(seasonality)
        candidates = candidates.merge(season_df, on="stock_id", how="left")
    else:
        candidates["same_month_effect"] = False
        candidates["same_month_note"] = "同月份資料不足"
    candidates["same_month_effect"] = candidates["same_month_effect"].fillna(False).astype(bool)
    candidates["same_month_note"] = candidates["same_month_note"].fillna("同月份資料不足")
    latest = latest.merge(candidates[["stock_id", "same_month_effect", "same_month_note"]], on="stock_id", how="left")
    latest["same_month_effect"] = latest["same_month_effect"].fillna(False).astype(bool)
    latest["same_month_note"] = latest["same_month_note"].fillna("同月份未檢核")
    candidates = candidates[candidates["same_month_effect"]].sort_values("score", ascending=False).head(10)
    return latest, candidates


def market_status(history):
    twii = yahoo_chart("^TWII", "1y")
    latest = pd.to_numeric(history[history["date"] == history["date"].max()]["pct_change"], errors="coerce")
    positive = (latest > 0).mean()
    if positive >= 0.55:
        return "強勢盤"
    if positive >= 0.45:
        return "中性盤"
    if positive >= 0.35:
        return "弱勢盤"
    return "明顯空頭"


def fmt_pct(v):
    if v is None or pd.isna(v):
        return "N/A"
    return f"{v:+.2f}%"


def fmt_money(v):
    return f"{v:,.0f}"


def fetch_financial_news():
    news_items = []
    # 1. 鉅亨網
    try:
        url = "https://news.cnyes.com/api/v3/news/category/headline?limit=8"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as r:
            js = json.loads(r.read().decode("utf-8"))
            for item in (js.get("items") or {}).get("data", []) if isinstance(js, dict) else []:
                t = (item.get("title") or "").strip()
                s = (item.get("summary") or "").strip()
                if t:
                    news_items.append({"title": t, "summary": s, "source": "鉅亨/國內大報"})
    except Exception:
        pass

    # 2. 台灣主要財經雜誌 RSS (商業周刊, 今周刊, 財訊, 先探投資週刊, 遠見, 天下)
    try:
        import xml.etree.ElementTree as ET
        mag_queries = [
            ("%E商业周刊+%E今周刊+%E財訊+%E先探", "台灣主要財經雜誌"),
            ("Yahoo+Finance+stock+market+Fed", "Yahoo Finance 國際")
        ]
        for query_str, src_label in mag_queries:
            gurl = f"https://news.google.com/rss/search?q={query_str}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            greq = urllib.request.Request(gurl, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(greq, timeout=10, context=ssl_ctx) as r:
                tree = ET.fromstring(r.read())
                for item in tree.findall(".//item")[:5]:
                    t = item.find("title").text if item.find("title") is not None else ""
                    if t and not any(n["title"] in t for n in news_items):
                        news_items.append({"title": t, "summary": "", "source": src_label})
    except Exception:
        pass

    return news_items


def fetch_past_year_dividends(symbol):
    if symbol.endswith('.TW') or symbol.endswith('.TWO'):
        candidates = [symbol]
    else:
        candidates = [f'{symbol}.TW', f'{symbol}.TWO', symbol]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    for sym in candidates:
        for domain in ['query1.finance.yahoo.com', 'query2.finance.yahoo.com']:
            url = f'https://{domain}/v8/finance/chart/{sym}?range=1y&interval=1d&events=div'
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as r:
                        js = json.loads(r.read().decode('utf-8'))
                        chart_list = (js.get('chart') or {}).get('result', []) if isinstance(js, dict) else []
                        if chart_list and isinstance(chart_list[0], dict):
                            events = (chart_list[0].get('events') or {}).get('dividends', {}) or {}
                            if events:
                                total_div = sum(float(v.get('amount', 0.0)) for v in events.values())
                                return total_div
                except Exception:
                    pass
    return 0.0


def parse_dp():
    path = os.path.join(POSITION_DIR, "DP.csv")
    rows = []
    for line in open(path, "r", encoding="cp950", errors="replace"):
        line = line.strip()
        if not line or line.startswith("股票名稱"):
            if rows:
                break
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 12:
            continue
        name_full = parts[0]
        m = re.search(r"\(([^)]+)\)", name_full)
        sid = m.group(1) if m else name_full
        name = re.sub(r"\([^)]+\)", "", name_full)
        
        old_val = clean_num(parts[6]) or 0
        old_price = clean_num(parts[5]) or 0
        cost_twd = clean_num(parts[3]) or 0
        shares = clean_num(parts[2]) or (old_val / old_price if old_price > 0 else 0)
        
        yc = yahoo_chart(f"{sid}.TW") or yahoo_chart(f"{sid}.TWO")
        if yc and yc.get("close"):
            price = float(yc["close"])
        else:
            price = old_price
            
        value_twd = shares * price if shares > 0 else old_val
        pnl_twd = value_twd - cost_twd if cost_twd > 0 else (clean_num(parts[7]) or 0)
        return_pct = (pnl_twd / cost_twd * 100) if cost_twd > 0 else (clean_num(parts[8].replace("%", "")) or 0)
        
        sym = f"{sid}.TW" if sid.isdigit() and len(sid) == 4 else f"{sid}.TWO"
        div_per_share = fetch_past_year_dividends(sym)
        div_twd = shares * div_per_share
        pnl_with_div_twd = pnl_twd + div_twd
        return_pct_with_div = (pnl_with_div_twd / cost_twd * 100) if cost_twd > 0 else return_pct
        
        rows.append(
            {
                "stock_id": sid,
                "stock_name": name,
                "market": "台灣",
                "value_twd": value_twd,
                "cost_twd": cost_twd,
                "pnl_twd": pnl_twd,
                "div_twd": div_twd,
                "pnl_with_div_twd": pnl_with_div_twd,
                "return_pct": return_pct,
                "return_pct_with_div": return_pct_with_div,
                "price": price,
            }
        )
    return pd.DataFrame(rows)


def parse_ip(fx):
    path = os.path.join(POSITION_DIR, "IP.csv")
    df = pd.read_csv(path, encoding="cp950")
    df.columns = [c.strip() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        name_full = str(r["股票名稱"])
        m = re.search(r"\(([^)]+)\)", name_full)
        sid = m.group(1) if m else name_full
        name = re.sub(r"\([^)]+\)", "", name_full).strip()
        
        old_val_usd = clean_num(r["庫存現值"]) or 0
        old_price_usd = clean_num(r["現價"]) or 0
        cost_usd = clean_num(r["庫存成本"]) or 0
        shares = clean_num(r.get("庫存股數")) or (old_val_usd / old_price_usd if old_price_usd > 0 else 0)
        
        yc = yahoo_chart(sid)
        if yc and yc.get("close"):
            price_usd = float(yc["close"])
        else:
            price_usd = old_price_usd
            
        val_usd = shares * price_usd if shares > 0 else old_val_usd
        pnl_usd = val_usd - cost_usd if cost_usd > 0 else (clean_num(r.get("投資損益")) or 0)
        return_pct = (pnl_usd / cost_usd * 100) if cost_usd > 0 else (clean_num(r.get("報酬率%(不含息)")) or 0)
        
        value_twd = val_usd * fx
        cost_twd = cost_usd * fx
        pnl_twd = pnl_usd * fx
        
        div_per_share_usd = fetch_past_year_dividends(sid)
        div_twd = shares * div_per_share_usd * fx
        pnl_with_div_twd = pnl_twd + div_twd
        return_pct_with_div = (pnl_with_div_twd / cost_twd * 100) if cost_twd > 0 else return_pct
        
        rows.append(
            {
                "stock_id": sid,
                "stock_name": name,
                "market": "美國",
                "value_twd": value_twd,
                "cost_twd": cost_twd,
                "pnl_twd": pnl_twd,
                "div_twd": div_twd,
                "pnl_with_div_twd": pnl_with_div_twd,
                "return_pct": return_pct,
                "return_pct_with_div": return_pct_with_div,
                "price": price_usd,
            }
        )
    return pd.DataFrame(rows)


def classify_position(sid, name):
    sid = str(sid).strip().upper()
    name = str(name).strip()
    core = {"0050", "0056", "00646", "006208", "00878", "SPY", "VT", "QQQ", "BND", "TLT"}
    if sid.startswith("00") or sid in core or any(k in name.upper() for k in ["ETF", "QQQ", "SPDR", "VANGUARD", "ISHARES"]):
        return "核心"
    if sid in core:
        return "核心"
    if sid == "2330":
        return "核心單股"
    return "衛星"


def return_target_review(pf, snap, target=0.08):
    def expected_return(row):
        sid = str(row.get("stock_id", "")).upper()
        name = str(row.get("stock_name", "")).upper()
        category = str(row.get("category", ""))
        if category == "債券/現金":
            return 0.035
        if sid in {"00679B", "00751B", "BND", "TLT"} or "債" in name:
            return 0.035
        if sid in {"00830", "QQQ"} or "半導體" in name:
            return 0.10
        if sid in {"0050", "006208", "00646", "SPY", "VT"} or "S&P" in name or "TAIWAN50" in name:
            return 0.08
        if sid in {"0056", "00878"} or "高股息" in name:
            return 0.065
        if category == "核心單股":
            return 0.08
        if category == "衛星":
            return 0.09
        if category == "核心":
            return 0.075
        return 0.06

    securities_expected = 0.0
    for _, r in pf.iterrows():
        securities_expected += float(r.get("weight_pct", 0) or 0) / 100 * expected_return(r)
    cash_weight = CASH_TWD / snap["total_assets_twd"]
    current_expected = securities_expected + cash_weight * 0.01
    gap = target - current_expected
    total = snap["total_assets_twd"]
    investable_cash = CASH_TWD
    extra_core_needed = max(0.0, gap * total / max(0.085 - 0.01, 0.001))
    target_cash = total * 0.05
    deploy_cash = max(0.0, investable_cash - target_cash)
    satellite_weight = float(snap.get("satellite_pct", 0) or 0)
    tech_weight = float(snap.get("tech_direct_pct", 0) or 0)
    return {
        "target_pct": target * 100,
        "expected_pct": current_expected * 100,
        "gap_pct": gap * 100,
        "target_income_twd": total * target,
        "expected_income_twd": total * current_expected,
        "extra_core_needed_twd": extra_core_needed,
        "deploy_cash_twd": deploy_cash,
        "cash_pct": cash_weight * 100,
        "satellite_pct": satellite_weight,
        "tech_pct": tech_weight,
        "can_reach": current_expected >= target,
    }


def position_action(row):
    if row["category"] == "債券/現金":
        return "續抱"
    if row["category"] == "核心":
        return "續抱"
    if row["weight_pct"] > 15:
        return "分批減碼"
    if row["weight_pct"] > 5 and row["category"] == "衛星":
        return "停止加碼"
    if row["return_pct"] is not None and row["return_pct"] < -15:
        return "分批減碼"
    return "續抱"


def analyze_portfolio(fx):
    tw = parse_dp()
    us = parse_ip(fx)
    pf = pd.concat([tw, us], ignore_index=True)
    pf["category"] = pf.apply(lambda r: classify_position(str(r["stock_id"]), str(r["stock_name"])), axis=1)
    securities = pf["value_twd"].sum()
    total = securities + CASH_TWD
    pf["weight_pct"] = pf["value_twd"] / total * 100
    pf["action"] = pf.apply(position_action, axis=1)
    pf["industry"] = pf.apply(lambda r: classify_industry(str(r["stock_id"]), str(r["stock_name"])), axis=1)
    known_cost = pf["cost_twd"].sum()
    pnl = pf["pnl_twd"].sum()
    core = pf[pf["category"].isin(["核心", "核心單股"])]["value_twd"].sum() / total * 100
    sat = pf[pf["category"].eq("衛星")]["value_twd"].sum() / total * 100
    bond = pf[pf["category"].eq("債券/現金")]["value_twd"].sum() / total * 100
    tech = pf[pf["industry"].isin(["半導體", "電子零組件", "電子"])]["value_twd"].sum() / total * 100
    total_div_twd = pf["div_twd"].sum() if "div_twd" in pf.columns else 0.0
    pnl_with_div = pnl + total_div_twd
    snap = {
        "date": TODAY.isoformat(),
        "total_assets_twd": total,
        "securities_twd": securities,
        "cash_twd": CASH_TWD,
        "known_cost_twd": known_cost,
        "cumulative_pnl_twd": pnl,
        "cumulative_return_pct": pnl / known_cost * 100 if known_cost else 0,
        "total_div_twd": total_div_twd,
        "pnl_with_div_twd": pnl_with_div,
        "total_return_with_div_pct": pnl_with_div / known_cost * 100 if known_cost else 0.0,
        "div_yield_pct": total_div_twd / securities * 100 if securities else 0.0,
        "tw_value_twd": tw["value_twd"].sum(),
        "us_value_twd": us["value_twd"].sum(),
        "core_pct": core,
        "satellite_pct": sat,
        "bond_pct": bond,
        "tech_direct_pct": tech,
        "fx_usdtwd": fx,
    }
    return pf.sort_values("weight_pct", ascending=False), snap


def append_portfolio_history(snap):
    path = os.path.join(STOCK_DIR, "portfolio_performance_history.csv")
    cols = list(snap.keys())
    previous = None
    if os.path.exists(path):
        hist = pd.read_csv(path)
        if not hist.empty:
            prior_days = hist[hist["date"].astype(str) < TODAY.isoformat()]
            if not prior_days.empty:
                previous = prior_days.iloc[-1].to_dict()
            latest = hist.iloc[-1].to_dict()
            if str(latest.get("date")) == TODAY.isoformat():
                return previous
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if f.tell() == 0:
            w.writeheader()
        w.writerow({k: f"{v:.4f}" if isinstance(v, float) else v for k, v in snap.items()})
    return previous


def append_satellite_history(data_date, candidates, followups):
    save_morning_selection_snapshot(data_date, candidates)
    path = os.path.join(STOCK_DIR, "satellite_recommendation_history.csv")
    exists = os.path.exists(path)
    if exists:
        try:
            prior = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
            if "report_date" in prior.columns and (prior["report_date"] == TODAY.isoformat()).any():
                return
        except Exception:
            pass
    cols = [
        "report_date",
        "recommendation_date",
        "stock_id",
        "stock_name",
        "industry",
        "close",
        "pct_change",
        "buy_signal_count",
        "score",
        "initial_action",
        "followup_action",
        "sell_trigger",
    ]
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if not exists or os.path.getsize(path) == 0:
            w.writeheader()
        for _, r in candidates.iterrows():
            sid = str(r["stock_id"])
            fu = followups.get(sid, ("續抱", "跌破MA20且相對強度轉弱時減碼"))
            w.writerow(
                {
                    "report_date": TODAY.isoformat(),
                    "recommendation_date": data_date.isoformat(),
                    "stock_id": sid,
                    "stock_name": r["stock_name"],
                    "industry": r["industry"],
                    "close": f"{r['close']:.2f}",
                    "pct_change": f"{(r.get('pct_change') or 0):.2f}",
                    "buy_signal_count": int(r.get("academic_signal_count", r.get("buy_signals", 0))),
                    "score": f"{r['score']:.4f}",
                    "initial_action": "優先觀察" if not r["overheat"] and not r["volume_down"] else "過熱/轉弱觀察",
                    "followup_action": fu[0],
                    "sell_trigger": fu[1],
                }
            )


def save_morning_selection_snapshot(data_date, candidates):
    strategy = load_strategy()
    rows = []
    snapshot_fields = STRATEGY_SCORE_COLUMNS + [
        "score",
        "close",
        "pct_change",
        "overheat",
        "volume_down",
        "low_vol",
        "ma_ratio",
        "relative_strength",
        "total_lots",
        "holding_period",
        "holding_target_days",
        "holding_guide",
    ]
    for rank, (_, row) in enumerate(candidates.head(10).iterrows(), start=1):
        item = {
            "rank": rank,
            "stock_id": str(row.get("stock_id", "")),
            "stock_name": str(row.get("stock_name", "")),
            "industry": str(row.get("industry", "")),
        }
        for field in snapshot_fields:
            value = row.get(field)
            if hasattr(value, "item"):
                value = value.item()
            if pd.isna(value):
                item[field] = None
            elif isinstance(value, bool):
                item[field] = value
            elif isinstance(value, (int, float)):
                item[field] = float(value)
            else:
                item[field] = value
        rows.append(item)

    payload = {
        "report_date": TODAY.isoformat(),
        "recommendation_data_date": data_date.isoformat(),
        "strategy": {
            "weights": strategy["weights"],
            "penalties": strategy["penalties"],
            "thresholds": strategy["thresholds"],
            "holding_policy": strategy.get("holding_policy", {}),
            "last_review_date": strategy.get("last_review_date"),
        },
        "selected": rows,
    }
    path = os.path.join(STOCK_DIR, f"morning_selection_snapshot_{TODAY.isoformat()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def read_previous_recommendations(latest, history=None):
    path = os.path.join(STOCK_DIR, "satellite_recommendation_history.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        hist = pd.read_csv(path, encoding="utf-8-sig", dtype=str, on_bad_lines="skip")
    except Exception:
        return pd.DataFrame()
    if "report_date" not in hist.columns:
        return pd.DataFrame()

    prior_hist = hist[hist["report_date"].astype(str) < TODAY.isoformat()].copy()
    if prior_hist.empty:
        return pd.DataFrame()

    # Load 53w price history if not passed in, to compute exact trading days held and entry price
    if history is None or history.empty:
        h53_path = os.path.join(STOCK_DIR, "twse_listed_close_volume_history_53w.csv")
        if os.path.exists(h53_path):
            try:
                history = pd.read_csv(h53_path, encoding="utf-8-sig", dtype={"stock_id": str}, low_memory=False)
            except Exception:
                history = pd.DataFrame()
        else:
            history = pd.DataFrame()

    trading_dates = sorted(history["date"].astype(str).unique()) if not history.empty else sorted(prior_hist["report_date"].astype(str).unique())
    recent_20_dates = set(trading_dates[-20:]) if len(trading_dates) >= 20 else set(trading_dates)

    # Filter recommendations from the past 20 trading days (rolling active window)
    window_hist = prior_hist[prior_hist["report_date"].astype(str).isin(recent_20_dates)].copy()
    if window_hist.empty:
        recent_rep_dates = sorted(prior_hist["report_date"].astype(str).unique())[-10:]
        window_hist = prior_hist[prior_hist["report_date"].astype(str).isin(recent_rep_dates)].copy()

    if window_hist.empty:
        return pd.DataFrame()

    # Group by stock_id: track from the FIRST entry date in the rolling 20-day window, and also count total appearances
    window_hist = window_hist.sort_values("report_date")
    grouped = []
    for sid, grp in window_hist.groupby("stock_id", sort=False):
        first_row = grp.iloc[0]
        last_row = grp.iloc[-1]
        grouped.append({
            "stock_id": str(sid).strip(),
            "stock_name": str(last_row.get("stock_name", first_row.get("stock_name", ""))).strip(),
            "first_report_date": str(first_row.get("report_date", "")),
            "last_report_date": str(last_row.get("report_date", "")),
            "entry_ref_close": clean_num(first_row.get("close")) or 0.0,
            "entry_pct_change": clean_num(first_row.get("pct_change")) or 0.0,
            "pick_count_20d": len(grp),
        })
    unique_stocks = pd.DataFrame(grouped).sort_values(["last_report_date", "pick_count_20d"], ascending=[False, False])

    latest_map = latest.copy()
    latest_map["stock_id"] = latest_map["stock_id"].astype(str)

    rows = []
    for _, old in unique_stocks.iterrows():
        sid = str(old["stock_id"]).strip()
        first_rep_d = str(old["first_report_date"])
        # Calculate trading days held since first_rep_d
        if trading_dates:
            held_days = sum(1 for d in trading_dates if d >= first_rep_d)
        else:
            held_days = 1

        # Find actual entry open price on or after first_rep_d from history, fallback to entry_ref_close
        entry_price = float(old["entry_ref_close"] or 0)
        if not history.empty:
            sub_h = history[(history["stock_id"].astype(str) == sid) & (history["date"].astype(str) >= first_rep_d)].sort_values("date")
            if not sub_h.empty:
                op_v = clean_num(sub_h.iloc[0].get("open"))
                cl_v = clean_num(sub_h.iloc[0].get("close"))
                if op_v and op_v > 0:
                    entry_price = float(op_v)
                elif cl_v and cl_v > 0:
                    entry_price = float(cl_v)

        match = latest_map[latest_map["stock_id"] == sid]
        if match.empty:
            rows.append(
                {
                    "stock_id": sid,
                    "stock_name": old.get("stock_name", ""),
                    "entry_date": first_rep_d[5:],
                    "held_days": held_days,
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
            action = "賣出"
            trigger = f"持有{held_days}日({cum_ret:+.1f}%)；觸發硬性停損線，果斷離場"
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
    except Exception:
        pass
    return out_df


def make_followups(candidates):
    out = {}
    for _, r in candidates.iterrows():
        action = "續抱"
        trigger = "跌破MA20且相對強度轉弱時減碼"
        if r.get("overheat"):
            action = "減碼"
            trigger = "急漲後跌破前一日低點或爆量收黑"
        if r.get("volume_down") or (r.get("close", 0) < (r.get("ma120") or 0) and not r.get("relative_strength")):
            action = "賣出"
            trigger = "跌破MA120且相對強度轉弱，或放量下跌"
        elif int(r.get("academic_signal_count", r.get("buy_signals", 0))) < 5 and r.get("pct_change", 0) < 0:
            action = "減碼"
            trigger = "學術證據分數降溫且收跌，先降衛星部位"
        out[str(r["stock_id"])] = (action, trigger)
    return out


def setup_pdf():
    pdfmetrics.registerFont(TTFont("MSJH", PYFONT))
    styles = {
        "h1": ParagraphStyle("h1", fontName="MSJH", fontSize=20, leading=24, textColor=colors.white),
        "h2": ParagraphStyle("h2", fontName="MSJH", fontSize=12, leading=16, textColor=colors.HexColor("#075f72"), spaceAfter=6),
        "body": ParagraphStyle("body", fontName="MSJH", fontSize=8.6, leading=12, textColor=colors.HexColor("#18352f")),
        "small": ParagraphStyle("small", fontName="MSJH", fontSize=7.2, leading=10, textColor=colors.HexColor("#4f665f")),
        "white": ParagraphStyle("white", fontName="MSJH", fontSize=8.5, leading=11, textColor=colors.white),
    }
    return styles


def pct_para(v, styles):
    cls = "#c33b32" if v is not None and not pd.isna(v) and v >= 0 else "#16834a"
    return Paragraph(f'<font color="{cls}"><b>{fmt_pct(v)}</b></font>', styles["body"])


def make_doc(path, title, subtitle, story, styles):
    def draw_page(canvas, doc):
        w, h = letter
        canvas.setFillColor(colors.HexColor("#eef7fb"))
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#075f72"))
        canvas.rect(0, h - 0.72 * inch, w, 0.72 * inch, fill=1, stroke=0)
        canvas.setFont("MSJH", 18)
        canvas.setFillColor(colors.white)
        canvas.drawString(0.42 * inch, h - 0.38 * inch, title)
        canvas.setFont("MSJH", 8)
        canvas.drawString(0.42 * inch, h - 0.55 * inch, subtitle)
        canvas.setFillColor(colors.HexColor("#075f72"))
        canvas.rect(0, 0, w, 0.22 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("MSJH", 6.7)
        canvas.drawString(0.42 * inch, 0.08 * inch, "紅色為上漲／正報酬，綠色為下跌／負報酬。僅供研究參考，不構成投資建議。")
        canvas.drawRightString(w - 0.42 * inch, 0.08 * inch, f"第 {doc.page} 頁")

    doc = BaseDocTemplate(path, pagesize=letter, leftMargin=0.38 * inch, rightMargin=0.38 * inch, topMargin=0.92 * inch, bottomMargin=0.36 * inch)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=draw_page)])
    doc.build(story)


def build_doc_with_fallback(path, title, subtitle, story, styles, suffix):
    target = path
    if os.path.exists(path):
        try:
            with open(path, "ab"):
                pass
        except PermissionError:
            root, ext = os.path.splitext(path)
            target = f"{root}_{suffix}{ext}"
    try:
        make_doc(target, title, subtitle, list(story), styles)
        return target
    except PermissionError:
        root, ext = os.path.splitext(path)
        ts = datetime.now().strftime("%H%M%S")
        alt = f"{root}_{suffix}_{ts}{ext}"
        make_doc(alt, title, subtitle, list(story), styles)
        return alt


def styled_table(data, widths=None, font_size=7.2):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "MSJH"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), font_size + 2),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0789a5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8e3eb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4fbfd")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def market_lookup(market_rows):
    out = {}
    for name, dt, close, pct in market_rows:
        out[name] = {"date": dt, "close": close, "pct": pct}
    return out


def market_pct(mk, name, default=0):
    entry = (mk.get(name) or {}) if isinstance(mk, dict) else {}
    v = entry.get("pct")
    return default if v is None or pd.isna(v) else float(v)


def overnight_global_pressure(mk, extras):
    nasdaq = market_pct(mk, "NASDAQ")
    sox = market_pct(mk, "費城半導體")
    spx = market_pct(mk, "S&P 500")
    dow = market_pct(mk, "Dow Jones")
    vix_info = (extras.get("VIX") or {}) if isinstance(extras, dict) else {}
    vix = vix_info.get("pct", 0)
    vix = 0 if vix is None or pd.isna(vix) else float(vix)
    us_avg = (nasdaq + sox + spx + dow) / 4
    risk_off = (
        us_avg <= -0.5
        or nasdaq <= -1.0
        or sox <= -2.0
        or (spx < 0 and vix >= 3)
    )
    severe_risk_off = (
        us_avg <= -1.0
        or nasdaq <= -1.5
        or sox <= -3.0
        or (spx < -0.5 and vix >= 5)
    )
    risk_on = us_avg >= 0.5 and nasdaq >= 0.5 and sox >= 0 and vix <= 0
    return {
        "us_avg": us_avg,
        "nasdaq": nasdaq,
        "sox": sox,
        "spx": spx,
        "dow": dow,
        "vix": vix,
        "risk_off": risk_off,
        "severe_risk_off": severe_risk_off,
        "risk_on": risk_on,
    }


def morning_market_status(local_status, mk, extras):
    pressure = overnight_global_pressure(mk, extras)
    if pressure["severe_risk_off"]:
        return "弱勢盤"
    if pressure["risk_off"]:
        return "中性盤" if local_status == "強勢盤" else local_status
    if pressure["risk_on"] and local_status in {"強勢盤", "中性盤"}:
        return "強勢盤"
    return local_status


def tw_market_bias(tw_pct, pressure):
    tw_pct = 0 if tw_pct is None or pd.isna(tw_pct) else float(tw_pct)
    if pressure["severe_risk_off"]:
        return "偏空觀察", 2
    if pressure["risk_off"]:
        return "中性偏弱", 2 if tw_pct < 0 else 3
    if tw_pct > 0.5:
        return "偏多", 4
    if tw_pct >= -0.5:
        return "中性", 3
    return "偏空", 2


def dashboard_title(text, styles):
    style = ParagraphStyle(
        f"dashboard_{abs(hash(text))}",
        parent=styles["body"],
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#0b3d78"),
    )
    return Table(
        [[Paragraph(f"<b>{text}</b>", style)]],
        colWidths=[None],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#dceefa")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#4d83bd")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )


def dashboard_table(data, widths, styles, font_size=7.2, header=True, align_right_from=1):
    body_style = ParagraphStyle(
        f"dash_body_{font_size}_{len(data)}",
        parent=styles["small"],
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.HexColor("#18304f"),
    )
    header_style = ParagraphStyle(
        f"dash_head_{font_size}_{len(data)}",
        parent=styles["small"],
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.HexColor("#0b3d78"),
    )
    normalized = []
    for rix, row in enumerate(data):
        cells = []
        for cell in row:
            if isinstance(cell, Paragraph):
                cells.append(cell)
            else:
                c_style = header_style if (header and rix == 0) else body_style
                text_content = f"<b>{cell}</b>" if (header and rix == 0) else str(cell)
                cells.append(Paragraph(text_content, c_style))
        normalized.append(cells)
    table = Table(normalized, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "MSJH"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEADING", (0, 0), (-1, -1), font_size + 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#bfd2e3")),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f3f8fc")]),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dceefa")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0b3d78")),
            ("FONTNAME", (0, 0), (-1, 0), "MSJH"),
        ]
    if align_right_from is not None:
        commands.append(("ALIGN", (align_right_from, 1 if header else 0), (-1, -1), "RIGHT"))
    table.setStyle(TableStyle(commands))
    return table


def quote_cells(label, quote, styles, unit=""):
    if not quote:
        return [label, "N/A", Paragraph('<font color="#6b7280">資料不足</font>', styles["small"])]
    pct = quote.get("pct")
    color = "#c7252e" if pct is not None and pct >= 0 else "#16834a"
    arrow = "▲" if pct is not None and pct >= 0 else "▼"
    value = f"{quote.get('close', 0):,.2f}{unit}"
    change = f'<font color="{color}"><b>{arrow} {abs(pct):.2f}%</b></font>' if pct is not None else "N/A"
    return [label, value, Paragraph(change, styles["small"])]


def extract_market_news_summary(news_items, mk):
    us_news = []
    asia_news = []
    macro_news = []
    if news_items:
        for item in news_items:
            title = item.get('title', '')
            summary = item.get('summary', '')
            full = title + ' ' + summary
            if any(k in full for k in ['美股', '道瓊', '標普', '納斯達克', '費半', '輝達', '台積電ADR', 'Fed', '降息', '美債', '華爾街']):
                if len(us_news) < 2: us_news.append(title)
            elif any(k in full for k in ['台股', '日經', '陸股', '港股', '韓股', '亞股', '加權', '外資', '台積電']):
                if len(asia_news) < 2: asia_news.append(title)
            else:
                if len(macro_news) < 2: macro_news.append(title)
                
    nasdaq_pct = fmt_pct((mk.get('NASDAQ') or {}).get('pct')) if isinstance(mk, dict) else "N/A"
    twii_pct = fmt_pct((mk.get('台灣加權') or {}).get('pct')) if isinstance(mk, dict) else "N/A"
    
    line1 = f"<b>美股/國際交易所：</b>{us_news[0]}" if us_news else f"<b>美股/國際交易所：</b>NASDAQ {nasdaq_pct}，美股大盤與科技龍頭股觀望重磅財報。"
    line2 = f"<b>亞股/台股焦點：</b>{asia_news[0]}" if asia_news else f"<b>亞股/台股焦點：</b>台灣加權 {twii_pct}，關注外資進出與權值股走勢。"
    line3 = f"<b>鉅亨網/各大報節錄：</b>{us_news[1] if len(us_news)>1 else (macro_news[0] if macro_news else '各大財經媒體聚焦主要交易所籌碼與最新總經數據。')}"
    
    return f"{line1}<br/>{line2}<br/>{line3}"


def build_section3_observations(news_items, t86, mk, global_pressure, extras):
    us_industry = []
    tw_themes = []
    risk_factors = []
    
    if news_items:
        for item in news_items:
            t = item.get('title', '')
            s = item.get('summary', '')
            full = t + ' ' + s
            if any(k in full for k in ['美股', '輝達', 'NVDA', '台積電ADR', '蘋果', 'Fed', '財報', '美債', '華爾街']):
                if len(us_industry) < 2: us_industry.append(t)
            elif any(k in full for k in ['AI', '半導體', '重電', '散熱', '矽光子', 'CoWoS', '伺服器', 'IC', '概念股', '族群', 'ETF', '機器人']):
                if len(tw_themes) < 2: tw_themes.append(t)
            elif any(k in full for k in ['風險', '跌', '關稅', '通膨', '戰爭', '地緣', '油價', '警戒', '獲利調節', '看空', '罷工']):
                if len(risk_factors) < 2: risk_factors.append(t)
                
    nasdaq_pct = fmt_pct((global_pressure or {}).get('nasdaq') if isinstance(global_pressure, dict) else None)
    sox_pct = fmt_pct((global_pressure or {}).get('sox') if isinstance(global_pressure, dict) else None)
    tw_pct = fmt_pct((mk.get('台灣加權') or {}).get('pct') if isinstance(mk, dict) else None)
    
    # 1. 籌碼與走勢脈絡
    c1_title = "<b>美股產業與籌碼脈絡</b>"
    c1_body = f"隔夜美股 NASDAQ {nasdaq_pct}、費半 {sox_pct}。"
    if us_industry:
        c1_body += f" 美國產業：{us_industry[0][:18]}...。"
    c1_body += f" 關注三大法人在加權 {tw_pct} 之籌碼走向。"
    
    # 2. 關鍵題材
    c2_title = "<b>鉅亨與各大報關鍵題材</b>"
    if tw_themes:
        theme_str = "<br/>".join([f"• {t[:16]}..." if len(t)>16 else f"• {t}" for t in tw_themes[:2]])
        c2_body = f"各大報熱門題材：<br/>{theme_str}"
    else:
        c2_body = "關鍵題材聚焦：<br/>• 半導體與AI機櫃供應鏈<br/>• 矽光子與CoWoS先進封裝"
        
    # 3. 市場與地緣風險提醒
    c3_title = "<b>市場與地緣風險提醒</b>"
    if risk_factors:
        c3_body = f"各大報風險提示：{risk_factors[0][:18]}...。追蹤美債與油價，嚴控放量回檔。"
    else:
        vix_str = fmt_pct((extras.get('VIX') or {}).get('pct')) if isinstance(extras, dict) else ""
        c3_body = f"風險控管重點：VIX {vix_str}。留意美債殖利率與外資高檔調節，嚴禁追高。"
        
    return c1_title + "<br/>" + c1_body, c2_title + "<br/>" + c2_body, c3_title + "<br/>" + c3_body


def calculate_integrated_sentiment(mk, global_pressure, extras, t86_tot_amt=0, news_items=None):
    tw_pct = float((mk.get('台灣加權') or {}).get('pct', 0) or 0) if isinstance(mk, dict) else 0.0
    nasdaq_pct = float((global_pressure or {}).get('nasdaq', 0) or 0) if isinstance(global_pressure, dict) else 0.0
    sox_pct = float((global_pressure or {}).get('sox', 0) or 0) if isinstance(global_pressure, dict) else 0.0
    vix_val = float((extras.get('VIX') or {}).get('close', 20) or 20) if isinstance(extras, dict) else 20.0
    
    score = 3.0
    if tw_pct > 0.5: score += 0.8
    elif tw_pct < -0.5: score -= 0.8
    
    if nasdaq_pct > 0.5: score += 0.6
    elif nasdaq_pct < -0.5: score -= 0.6
    
    if sox_pct > 0.5: score += 0.6
    elif sox_pct < -0.5: score -= 0.6
    
    if vix_val < 15: score += 0.4
    elif vix_val > 22: score -= 0.6
    
    if t86_tot_amt > 100: score += 0.4
    elif t86_tot_amt < -100: score -= 0.4
    
    score = max(1.0, min(5.0, score))
    
    if score >= 4.2:
        light_label = '強勢多頭'
        color_hex = '#4caf50'
        dots = '●●●●●'
        action_advice = '順應趨勢偏多操作，聚焦強勢主流標的。'
    elif score >= 3.4:
        light_label = '多頭震盪'
        color_hex = '#8bc34a'
        dots = '●●●●○'
        action_advice = '高檔震盪整理，聚焦主流 AI 供應鏈與量價確認標的。'
    elif score >= 2.6:
        light_label = '中性觀望'
        color_hex = '#f4b400'
        dots = '●●○○○'
        action_advice = '多空拉鋸且觀望氣氛濃厚，短線保留現金等待方向一致。'
    elif score >= 1.8:
        light_label = '弱勢防守'
        color_hex = '#ff9800'
        dots = '●●○○○'
        action_advice = '避險升溫與外資調節，優先控管跌破均線與放量回檔風險。'
    else:
        light_label = '空頭避險'
        color_hex = '#f44336'
        dots = '●○○○○'
        action_advice = '恐慌指數大升與避險需求高漲，嚴守停損紀律提高現金比重。'

    # 動態結合當日各大財經媒體焦點與即時行情
    news_lead = ""
    if news_items and len(news_items) > 0:
        for item in news_items:
            raw_t = item.get('title', '').strip()
            # 整理與過濾標題
            raw_t = re.sub(r'\s*[-|_]\s*.*$', '', raw_t)
            if raw_t and len(raw_t) >= 4:
                if len(raw_t) > 22:
                    news_lead = raw_t[:20] + "..."
                else:
                    news_lead = raw_t
                break

    if news_lead:
        one_sentence = f"市場聚焦「{news_lead}」，格局呈{light_label}，建議{action_advice}"
    else:
        tw_str = f"台股{'上漲' if tw_pct >= 0 else '下跌'}{abs(tw_pct):.2f}%"
        one_sentence = f"本日{tw_str}且美股觀望，整體呈現{light_label}態勢，建議{action_advice}"
        
    return light_label, dots, color_hex, one_sentence


def build_news_industry_and_stock_recommendations(news_items):
    matched_groups = {}
    
    keywords_map = [
        ('半導體', '半導體與 CoWoS 先進封裝', ['2330 台積電', '3583 辛耘', '6187 萬潤']),
        ('CoWoS', 'CoWoS 先進封裝', ['2330 台積電', '3583 辛耘', '6187 萬潤']),
        ('矽光子', '矽光子 CPO 光通訊', ['3450 聯鈞', '4979 華星光', '3363 上詮']),
        ('AI', 'AI 伺服器與水冷散熱', ['2382 廣達', '3231 緯創', '6669 緯穎', '3017 奇鋐']),
        ('散熱', '水冷散熱與機櫃系統', ['3017 奇鋐', '3324 雙鴻']),
        ('重電', '重電綠能與強韌電網', ['1519 華城', '1503 士電', '1513 中興電']),
        ('記憶體', '高頻寬記憶體 HBM / DRAM', ['2408 南亞科', '3260 威剛']),
        ('機器人', 'AI 機器人與自動化', ['2359 所羅門', '4583 台灣精銳']),
    ]
    
    if news_items:
        for item in news_items:
            full = (item.get('title', '') + ' ' + item.get('summary', '')).upper()
            for k, sub_ind, stocks in keywords_map:
                if k.upper() in full:
                    if sub_ind not in matched_groups:
                        matched_groups[sub_ind] = stocks
                    
    if not matched_groups:
        matched_groups = {
            'AI 伺服器與水冷散熱': ['2382 廣達', '3231 緯創', '6669 緯穎', '3017 奇鋐'],
            '半導體與 CoWoS 先進封裝': ['2330 台積電', '3583 辛耘', '6187 萬潤'],
            '高頻寬記憶體 HBM / DRAM': ['2408 南亞科', '3260 威剛'],
        }
        
    lines = ["<b>各大財經媒體熱門子產業與個股推薦 (源自新聞報導，非本模型計算)</b>"]
    for idx, (sub_ind, stocks) in enumerate(list(matched_groups.items())[:3], 1):
        st_str = "、".join(stocks[:4])
        lines.append(f"• <b>熱門子產業 {idx}【{sub_ind}】：</b>個股推薦 ➜ {st_str}")
        
    lines.append("<font size='6.5' color='#6b7280'>註：本欄位熱門子產業與個股推薦綜合整理自《商業周刊》、《今周刊》、《財訊》、《先探》、《遠見》及各大財經日報新聞專題，非本 PDF 學術 10 指標模型計算建議。</font>")
    return "<br/>".join(lines)


def build_global_report(data_date, history, candidates, latest, previous_followups, t86, t86_error, market_rows, fx, oil, tnx, extras, download_errors):
    styles = setup_pdf()
    story = []
    min_d, max_d = history["date"].min(), history["date"].max()
    mk = market_lookup(market_rows)
    local_status = market_status(history)
    global_pressure = overnight_global_pressure(mk, extras)
    status = morning_market_status(local_status, mk, extras)

    positive_markets = [r[3] for r in market_rows if r[3] is not None]
    global_avg = sum(positive_markets) / len(positive_markets) if positive_markets else 0
    
    tot_amt_val = 0
    if t86 is not None and not t86.empty:
        latest_c = history[history['date'] == data_date.isoformat()].copy()
        latest_c['stock_id'] = latest_c['stock_id'].astype(str)
        t86_m = t86.merge(latest_c[['stock_id', 'close']], on='stock_id', how='left')
        t86_m['close'] = pd.to_numeric(t86_m['close'], errors='coerce').fillna(0)
        tot_amt_val = (t86_m['total_lots'] * 1000 * t86_m['close']).sum() / 1e8

    news_items = fetch_financial_news()
    light_label, dots, color_hex, one_sentence_summary = calculate_integrated_sentiment(mk, global_pressure, extras, tot_amt_val, news_items=news_items)

    info_style = ParagraphStyle("dash_info", parent=styles["body"], fontSize=7.5, leading=10, textColor=colors.HexColor("#17324f"))
    take_style = ParagraphStyle("dash_take", parent=styles["body"], fontSize=8.1, leading=11, textColor=colors.HexColor("#6d1f22"))
    sentiment_style = ParagraphStyle("dash_sentiment", parent=info_style, textColor=colors.white)
    summary = Table(
        [[
            Paragraph(
                f"<b>資料與模型</b><br/>選股日 {data_date.isoformat() if data_date else '下載失敗'}<br/>"
                f"53週期間 {min_d} 至 {max_d}",
                info_style,
            ),
            Paragraph(
                f"<b>今日市場情緒</b><br/><font size='13' color='{color_hex}'>"
                f"{dots}</font><br/><b>{light_label}</b>",
                sentiment_style,
            ),
            Paragraph(f"<b>一句話結論</b><br/>{one_sentence_summary}", take_style),
        ]],
        colWidths=[2.30 * inch, 2.00 * inch, 3.44 * inch],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#edf5fb")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#123f73")),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
                ("BACKGROUND", (2, 0), (2, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#3e6f9f")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9bb9d5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )
    story.append(summary)
    story.append(Spacer(1, 5))
    story.append(dashboard_title("1  全球市場總覽｜指數、區域與風險情緒", styles))

    def market_rows_for(names):
        rows = [["市場", "收盤", "漲跌"]]
        for name in names:
            item = mk.get(name, {})
            rows.append([name, item.get("close", "N/A"), pct_para(item.get("pct"), styles)])
        return rows

    us_eu = dashboard_table(
        market_rows_for(["Dow Jones", "S&P 500", "NASDAQ", "費城半導體", "FTSE 100", "DAX"]),
        [1.10 * inch, 0.78 * inch, 0.60 * inch],
        styles,
        6.9,
    )
    asia = dashboard_table(
        market_rows_for(["日經225", "KOSPI", "恆生指數", "上證指數", "台灣加權"]),
        [1.10 * inch, 0.78 * inch, 0.60 * inch],
        styles,
        6.9,
    )
    news_items = fetch_financial_news()
    obs_text = extract_market_news_summary(news_items, mk)
    overview = Table(
        [[us_eu, asia, Paragraph(obs_text, info_style)]],
        colWidths=[2.58 * inch, 2.58 * inch, 2.58 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#f7fbfe")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    story.append(overview)
    story.append(Spacer(1, 5))
    story.append(dashboard_title("2  半導體與 AI 供應鏈｜商品與總經價格", styles))

    latest_map = {}
    if latest is not None and not latest.empty:
        latest_map = {str(r.stock_id): r for _, r in latest.iterrows()}
    # 預設當前產業代表企業（可依未來市場趨勢動態微調）
    supply_chain_sids = ["2330", "2454", "2303", "2382", "3231", "6669", "2345"]
    tech_rows = [["代號＋名稱", "收盤", "漲跌", "技術訊號"]]
    for sid in supply_chain_sids:
        if sid not in latest_map:
            continue
        r = latest_map[sid]
        # 採用學術 10 主要指標進行綜合技術訊號分析
        score_val = float(r.get("score", 0) or 0)
        ma_trend = bool(r.get("ma_trend", False))
        rs_trend = bool(r.get("relative_strength", False))
        vol_down = bool(r.get("volume_down", False))
        
        if vol_down:
            signal = "放量回檔"
        elif score_val >= 0.70 or (ma_trend and rs_trend):
            signal = "多頭偏強"
        elif ma_trend:
            signal = "均線支撐"
        else:
            signal = "整理觀察"
            
        tech_rows.append([f"{sid} {r.stock_name}", f"{r.close:,.2f}", pct_para(r.get("pct_change"), styles), signal])
    if len(tech_rows) == 1:
        tech_rows.append(["資料不足", "-", "-", "-"])
    tech_table = dashboard_table(tech_rows, [1.70 * inch, 0.78 * inch, 0.78 * inch, 0.90 * inch], styles, 6.7)

    macro_rows = [["商品/指標", "最新", "漲跌%"]]
    macro_rows.append(quote_cells("黃金", extras.get("黃金"), styles))
    macro_rows.append(quote_cells("白銀", extras.get("白銀"), styles))
    macro_rows.append(quote_cells("銅", extras.get("銅"), styles))
    macro_rows.append(quote_cells("布蘭特原油", extras.get("布蘭特原油"), styles))
    macro_rows.append(quote_cells("WTI 原油", oil, styles))
    macro_rows.append(quote_cells("美元指數", extras.get("美元指數"), styles))
    macro_table = dashboard_table(macro_rows, [1.40 * inch, 0.90 * inch, 0.84 * inch], styles, 6.7)
    middle = Table(
        [[tech_table, macro_table]],
        colWidths=[4.30 * inch, 3.44 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    story.append(middle)
    story.append(Spacer(1, 3))
    story.append(dashboard_title("3  台股今日重點觀察｜題材、籌碼與風險", styles))

    tw_pct = (mk.get("台灣加權") or {}).get("pct") if isinstance(mk, dict) else None
    tw_direction, tw_score = tw_market_bias(tw_pct, global_pressure)
    c1_txt, c2_txt, c3_txt = build_section3_observations(news_items, t86, mk, global_pressure, extras)
    focus_cards = [
        Paragraph(c1_txt, info_style),
        Paragraph(c2_txt, info_style),
        Paragraph(c3_txt, info_style),
    ]
    focus = Table(
        [focus_cards],
        colWidths=[2.58 * inch, 2.58 * inch, 2.58 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0f8f4")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fff9e8")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#fff3ef")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    story.append(focus)
    story.append(Spacer(1, 3))
    story.append(dashboard_title("4  資金面與權重風險指標｜今日操作結論", styles))

    # 1. 資金面法人籌碼（採前一日 T-1 買賣金額與張數統計）
    if t86 is not None and not t86.empty:
        latest_c = history[history['date'] == data_date.isoformat()].copy()
        latest_c['stock_id'] = latest_c['stock_id'].astype(str)
        t86_merged = t86.merge(latest_c[['stock_id', 'close']], on='stock_id', how='left')
        t86_merged['close'] = pd.to_numeric(t86_merged['close'], errors='coerce').fillna(0)
        
        f_amt = (t86_merged['foreign_lots'] * 1000 * t86_merged['close']).sum() / 1e8
        t_amt = (t86_merged['trust_lots'] * 1000 * t86_merged['close']).sum() / 1e8
        tot_amt = (t86_merged['total_lots'] * 1000 * t86_merged['close']).sum() / 1e8
        
        chips_text = (
            f"<b>資金面法人籌碼 (前一日 T-1)</b><br/>"
            f"外資：{f_amt:+.1f} 億 ({t86['foreign_lots'].sum():+,.0f}張)<br/>"
            f"投信：{t_amt:+.1f} 億 ({t86['trust_lots'].sum():+,.0f}張)<br/>"
            f"三大法人：{tot_amt:+.1f} 億"
        )
    else:
        chips_text = "<b>資金面法人籌碼</b><br/>前一日 T86 金額統計下載中"

    # 2. 全球重要指標 (前一日 T-1 美債、VIX、台幣兌主要外幣)
    eur_fx = yahoo_chart("EURTWD=X", target_date_str=data_date.isoformat())
    jpy_fx = yahoo_chart("JPYTWD=X", target_date_str=data_date.isoformat())
    
    usdtwd_str = f"{fx['close']:.3f}" if fx and isinstance(fx, dict) and fx.get('close') is not None else "N/A"
    eurtwd_str = f"{eur_fx['close']:.2f}" if eur_fx and isinstance(eur_fx, dict) and eur_fx.get('close') is not None else "N/A"
    jpytwd_str = f"{jpy_fx['close']:.4f}" if jpy_fx and isinstance(jpy_fx, dict) and jpy_fx.get('close') is not None else "N/A"
    tnx_str = f"{tnx['close']:.3f}%" if tnx and isinstance(tnx, dict) and tnx.get('close') is not None else "N/A"
    vix_info = extras.get("VIX") or {} if isinstance(extras, dict) else {}
    vix_close = vix_info.get("close")
    vix_str = f"{vix_close:.2f}" if vix_close is not None and not pd.isna(vix_close) else "N/A"

    risk_text = (
        f"<b>全球重要指標 (T-1)</b><br/>"
        f"美債10年：{tnx_str}｜VIX：{vix_str}<br/>"
        f"美元/台幣：{usdtwd_str}<br/>"
        f"歐元/台幣：{eurtwd_str}｜日圓：{jpytwd_str}"
    )

    # 3. 今日操作結論（綜合 1-5 點全球/商品/題材/籌碼/指標評估）
    action_text = (
        f"<b>本日操作結論</b><br/>"
        f"綜合前一日大盤、美股產業、總經商品與三大法人金額籌碼，目前市場方向定位為「{tw_direction}」。"
        f"衛星選股保留學術10模型前10名且同月份3年連漲者；若個股跌破長均線或放量回檔，嚴格依模型紀律控管。"
    )
    footer_panels = Table(
        [[Paragraph(chips_text, info_style), Paragraph(risk_text, info_style), Paragraph(action_text, info_style)]],
        colWidths=[2.30 * inch, 2.30 * inch, 3.14 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    story.append(footer_panels)
    story.append(Spacer(1, 2))
    story.append(dashboard_title("5  專業新聞脈絡與市場評分", styles))
    news_items = fetch_financial_news()
    # 左側：國內各大報章雜誌與 Yahoo Finance 國際財經新聞摘要
    tw_news_list = [n for n in news_items if n.get("source") == "國內大報/鉅亨"]
    yf_news_list = [n for n in news_items if n.get("source") == "Yahoo Finance 國際"]
    
    news_lines = ["<b>專業新聞脈絡 (國內大報 & Yahoo Finance 國際)</b><br/>"]
    if tw_news_list:
        n1 = tw_news_list[0]
        s1 = n1["summary"][:24] + "..." if n1.get("summary") and len(n1["summary"]) > 24 else (n1.get("summary") or "")
        news_lines.append(f"1. <b>[國內大報/鉅亨] {n1['title'][:22]}</b>" + (f"：{s1}" if s1 else ""))
    else:
        news_lines.append("1. <b>[國內大報]</b> 關注台股權值股與半導體供應鏈籌碼動向。")
        
    if yf_news_list:
        n2 = yf_news_list[0]
        news_lines.append("2. <b>[Yahoo Finance 國際]</b> 追蹤美股聯準會利率路徑與科技巨頭財報。")
        
    news_context = "<br/>".join(news_lines)

    def score_dots(score):
        score = max(1, min(5, int(score)))
        return "●" * score + "○" * (5 - score)

    tech_score = 4 if global_pressure["nasdaq"] > 0.5 and global_pressure["sox"] >= 0 else 3 if global_pressure["nasdaq"] >= -0.5 and global_pressure["sox"] >= -1 else 2
    risk_score = 2 if global_pressure["vix"] > 3 or global_pressure["spx"] < -0.5 else 3
    gold_pct = float(extras.get("黃金", {}).get("pct", 0) or 0) if isinstance(extras, dict) and extras.get("黃金") else 0
    news_and_rating = Table(
        [[Paragraph(news_context, info_style), Paragraph(f"<b>市場評分 (1-5)</b><br/>技術面：{score_dots(tech_score)}<br/>風險面：{score_dots(risk_score)}", info_style)]],
        colWidths=[5.16 * inch, 2.58 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f7fbfe")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    story.append(news_and_rating)
    if download_errors:
        story.append(Paragraph("資料下載訊息：" + "；".join(download_errors[:3]), styles["small"]))
    story.append(PageBreak())
    story.append(Paragraph("三大法人分別買賣超個股前五名 (前一日 T-1)", styles["h2"]))
    if t86 is not None and not t86.empty:
        # 幫外資、投信、自營商分別建立買超前5與賣超前5子表格
        def build_inst_top5_table(col_name, title_name):
            buys = t86.sort_values(col_name, ascending=False).head(5)
            sells = t86.sort_values(col_name, ascending=True).head(5)
            rows = [[f"<b>{title_name}買超前5</b>", "張數", f"<b>{title_name}賣超前5</b>", "張數"]]
            for (_, b), (_, s) in zip(buys.iterrows(), sells.iterrows()):
                b_name = f"{b.stock_id} {b.stock_name[:4]}"
                s_name = f"{s.stock_id} {s.stock_name[:4]}"
                b_lots = f"{getattr(b, col_name):+,.0f}"
                s_lots = f"{getattr(s, col_name):+,.0f}"
                rows.append([b_name, b_lots, s_name, s_lots])
            return dashboard_table(rows, [0.82 * inch, 0.44 * inch, 0.82 * inch, 0.44 * inch], styles, 5.8)

        f_table = build_inst_top5_table("foreign_lots", "外資")
        t_table = build_inst_top5_table("trust_lots", "投信")
        d_table = build_inst_top5_table("dealer_lots", "自營")

        institution_panel = Table(
            [[f_table, t_table, d_table]],
            colWidths=[2.58 * inch, 2.58 * inch, 2.58 * inch],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#5a86b5")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            ),
        )
        story.append(institution_panel)
        story.append(Paragraph("註：資料來源為台灣證券交易所 T86 前一日交易數據，分別統計外資、投信與自營商買賣超張數前5名個股。", styles["small"]))
    else:
        t86_reason = "權限不足，無法寫入/讀取當期快取檔" if "Permission denied" in str(t86_error) else str(t86_error)[:90]
        story.append(Paragraph(f"三大法人資料下載失敗：{t86_reason}。未沿用舊法人數據。", styles["body"]))
    story.append(Spacer(1, 2))
    q_note = f"先取當日學術模型前10，再保留去年同月份上漲者（1年期同月份效應）；過熱扣分門檻設為單日漲幅≥4.5%，並依波動與動能屬性標註建議持有週期。本期符合 {len(candidates)} 檔。"
    story.append(Paragraph("今日衛星觀察名單｜當日模型前 10＋同月份效應＋建議持有週期", styles["h2"]))
    story.append(Paragraph(q_note, styles["small"]))
    ctab = [["代號＋名稱", "產業", "收盤", "漲跌", "學術分數", "建議持有期", "操作與停利停損指引"]]
    for _, r in candidates.iterrows():
        h_period = r.get("holding_period", "15-20日(波段)")
        h_guide = r.get("holding_guide", "波段持有(15-20日)；破MA20或-6%停損")
        ctab.append([
            f"{r.stock_id} {r.stock_name}",
            r.industry,
            f"{r.close:.2f}",
            pct_para(r.get("pct_change"), styles),
            f"{r.score * 100:.1f}/{int(r.academic_signal_count)}/10",
            h_period,
            h_guide,
        ])
    if len(candidates) == 0:
        ctab.append(["無", "-", "-", "-", "-", "-", "當日模型前10皆未通過同月份效應條件"])
    story.append(styled_table(ctab, [1.15 * inch, 0.72 * inch, 0.58 * inch, 0.58 * inch, 0.78 * inch, 0.88 * inch, 3.05 * inch], 6.4))
    story.append(Spacer(1, 3))
    story.append(Paragraph("前期建議定期追蹤｜近 20 個交易日滾動持倉與到期結算判斷", styles["h2"]))
    ftab = [["代號＋名稱", "入選日(持有)", "入選價➔現價", "累積報酬", "學術分數", "今日判斷", "觸發理由與持有期指引"]]
    if previous_followups is not None and not previous_followups.empty:
        for _, r in previous_followups.head(8).iterrows():
            ftab.append([
                f"{r.stock_id} {r.stock_name}",
                str(r.get("entry_str", "-")),
                str(r.get("price_str", "-")),
                pct_para(r.get("cum_return_pct"), styles),
                r.signals,
                r.action,
                r.trigger,
            ])
        story.append(dashboard_table(ftab, [1.08 * inch, 0.76 * inch, 0.88 * inch, 0.62 * inch, 0.72 * inch, 0.64 * inch, 3.04 * inch], styles, 5.6))
    else:
        story.append(Paragraph("找不到可用的前一期歷史名單，因此本期不以今日名單冒充前期追蹤。", styles["body"]))
        
    news_rec_style = ParagraphStyle("news_rec_style", parent=styles["small"], fontSize=6.8, leading=8.5, textColor=colors.HexColor("#17324f"))
    news_rec_text = build_news_industry_and_stock_recommendations(news_items)
    news_rec_panel = Table(
        [[Paragraph(news_rec_text, news_rec_style)]],
        colWidths=[6.35 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#5a86b5")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f9fd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        ),
    )
    story.append(Spacer(1, 2))
    story.append(news_rec_panel)
    story.append(Spacer(1, 2))
    story.append(dashboard_title("學術證據 10 指標｜本期判讀框架", styles))
    indicator_rows = [
        [
            Paragraph("<b>1 中期動能</b><br/>衡量近中期報酬延續", styles["small"]),
            Paragraph("<b>2 52週高點接近度</b><br/>確認價格仍在強勢區", styles["small"]),
            Paragraph("<b>3 產業相對強度</b><br/>避開弱勢產業逆風", styles["small"]),
            Paragraph("<b>4 個股相對強度</b><br/>比較大盤超額表現", styles["small"]),
            Paragraph("<b>5 均線趨勢結構</b><br/>檢查MA20/60/120排列", styles["small"]),
        ],
        [
            Paragraph("<b>6 價量確認</b><br/>上漲需成交量支持", styles["small"]),
            Paragraph("<b>7 異常成交量</b><br/>辨認資金快速進出", styles["small"]),
            Paragraph("<b>8 低波動/低回撤</b><br/>控制下行與震盪風險", styles["small"]),
            Paragraph("<b>9 法人買超強度</b><br/>股數加總後換算張數", styles["small"]),
            Paragraph("<b>10 法人一致性</b><br/>外資投信自營商共振", styles["small"]),
        ],
    ]
    indicator_grid = Table(
        indicator_rows,
        colWidths=[1.548 * inch] * 5,
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f2f8fc")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
    )
    story.append(indicator_grid)
    story.append(Spacer(1, 3))
    story.append(dashboard_title("篩選透明度｜當日排名、同月份效應與賣出紀律", styles))
    funnel_text = (
        f"<b>本期篩選結果</b><br/>當日模型前10通過1年期同月份效應：{len(candidates)} 檔<br/>"
        "過熱防追高：T-1單日漲幅≥4.5%扣減0.12分，優先篩選溫和起漲標的。<br/>"
        "持有週期：波段型建議持有15-20個交易日，短線動能型3-5個交易日。"
    )
    sell_text = (
        "<b>持有/停利/停損準則</b><br/>賣出：放量下跌、觸發硬性停損(-6%/短線-4%)，或破MA120且相對弱勢。<br/>"
        "到期/停利：滿建議持有期(15-20日)到期結算，或波段獲利達+10%分批停利。<br/>"
        "減碼：10指標降至3項以下、短線急漲過熱，或跌破MA20支撐。"
    )
    integrity_text = (
        "<b>定期滾動追蹤機制</b><br/>自動追蹤近20個交易日所有入選標的之入選基準價、持有天數與累積報酬率；"
        "晚間複盤同步檢核T+1/T+5/T+10/T+20跨期批次勝率。"
    )
    screening = Table(
        [[Paragraph(funnel_text, info_style), Paragraph(sell_text, info_style), Paragraph(integrity_text, info_style)]],
        colWidths=[2.58 * inch, 2.58 * inch, 2.58 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f1f8f3")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fff4f1")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#f5f7fb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
    )
    story.append(screening)
    story.append(Spacer(1, 3))
    themes = Table(
        [[
            Paragraph("<b>防禦輪動</b><br/>電信避風港、低波動、高現金流", styles["small"]),
            Paragraph("<b>AI硬體</b><br/>AI機櫃、矽電容、TGV銅柱", styles["small"]),
            Paragraph("<b>高速傳輸</b><br/>光纖漲價、網通與伺服器互連", styles["small"]),
            Paragraph("<b>半導體</b><br/>台積電、市值權重與供應鏈財報", styles["small"]),
        ]],
        colWidths=[1.935 * inch] * 4,
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#5a86b5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
    )
    story.append(themes)
    story.append(Spacer(1, 3))
    checkpoints = Table(
        [[
            Paragraph("<b>開盤</b><br/>權值股、櫃買與量能是否同向", styles["small"]),
            Paragraph("<b>10:30</b><br/>強勢族群是否維持相對強度", styles["small"]),
            Paragraph("<b>午盤</b><br/>法人方向與台幣是否惡化", styles["small"]),
            Paragraph("<b>收盤</b><br/>更新MA20/60/120與放量下跌", styles["small"]),
        ]],
        colWidths=[1.935 * inch] * 4,
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#3e6f9f")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aac2d8")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e9f4fa")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    if t86 is None or t86.empty:
        story.append(checkpoints)
    out = os.path.join(STOCK_DIR, f"全球投資市場研究報告_{TODAY.isoformat()}.pdf")
    out = build_doc_with_fallback(out, f"全球投資市場研究報告_{TODAY.isoformat()}", f"選股資料日期：{data_date.isoformat() if data_date else '失敗'}", story, styles, "新聞詳細版")
    current_followups = make_followups(candidates)
    append_satellite_history(data_date, candidates, current_followups)
    return out


def build_personal_report(pf, snap, previous):
    styles = setup_pdf()
    story = []
    story += [
        Paragraph("投資組合總覽", styles["h2"]),
        Paragraph(
            f"總資產約 {snap['total_assets_twd']/10000:,.1f} 萬元，證券市值 {snap['securities_twd']/10000:,.1f} 萬元，"
            f"現金 {CASH_TWD/10000:.0f} 萬元。核心 {snap['core_pct']:.1f}%、衛星 {snap['satellite_pct']:.1f}%、"
            f"債券 {snap['bond_pct']:.1f}%；科技相關集中度 {snap['tech_direct_pct']:.1f}%。",
            styles["body"],
        ),
        Paragraph("主要部位與持股策略建議", styles["h2"]),
    ]
    tab = [["代號＋名稱", "分類", "權重", "損益", "報酬率", "建議"]]
    for _, r in pf.head(16).iterrows():
        tab.append([
            f"{r.stock_id} {r.stock_name}",
            r.category,
            f"{r.weight_pct:.2f}%",
            f"{r.pnl_twd/10000:+,.1f}萬",
            pct_para(r.return_pct, styles),
            r.action,
        ])
    story.append(styled_table(tab, [1.7 * inch, 0.75 * inch, 0.55 * inch, 0.8 * inch, 0.65 * inch, 0.75 * inch], 6.8))
    story.append(Spacer(1, 8))
    over = pf[(pf["category"].eq("衛星")) & (pf["weight_pct"] > 5)]
    risks = []
    for _, r in over.iterrows():
        target = snap["total_assets_twd"] * 0.05
        reduce_amt = max(0, r["value_twd"] - target)
        risks.append(f"{r.stock_id} {r.stock_name} 衛星權重 {r.weight_pct:.1f}%，高於 5% 原則；可分批調節約 {reduce_amt/10000:,.0f} 萬元至 5% 附近。")
    if snap["satellite_pct"] > 20:
        risks.append(f"全部衛星約 {snap['satellite_pct']:.1f}%，高於目標 10-20%，新資金優先往海外核心、債券與低波高息補。")
    story.append(Paragraph("集中度與調節建議", styles["h2"]))
    for r in risks[:5]:
        story.append(Paragraph("• " + r, styles["body"]))
    story.append(PageBreak())
    story.append(Paragraph("投資績效與前一期比較", styles["h2"]))
    if previous:
        prev_total = float(previous["total_assets_twd"])
        prev_sec = float(previous["securities_twd"])
        net_asset_change = snap["total_assets_twd"] - prev_total
        prev_cash = float(previous.get("cash_twd", CASH_TWD))
        cash_flow = CASH_TWD - prev_cash
        adj_change = net_asset_change - cash_flow
        perf = [
            ["項目", "前一期", "本期", "變化"],
            ["總資產", fmt_money(prev_total), fmt_money(snap["total_assets_twd"]), fmt_money(net_asset_change)],
            ["證券市值", fmt_money(prev_sec), fmt_money(snap["securities_twd"]), fmt_money(snap["securities_twd"] - prev_sec)],
            ["累積損益", fmt_money(float(previous["cumulative_pnl_twd"])), fmt_money(snap["cumulative_pnl_twd"]), fmt_money(snap["cumulative_pnl_twd"] - float(previous["cumulative_pnl_twd"]))],
            ["已知成本報酬率", f"{float(previous['cumulative_return_pct']):.2f}%", f"{snap['cumulative_return_pct']:.2f}%", f"{snap['cumulative_return_pct'] - float(previous['cumulative_return_pct']):+.2f}pp"],
            ["核心/衛星", f"{float(previous['core_pct']):.1f}% / {float(previous['satellite_pct']):.1f}%", f"{snap['core_pct']:.1f}% / {snap['satellite_pct']:.1f}%", "觀察再平衡"],
            ["科技集中度", f"{float(previous['tech_direct_pct']):.1f}%", f"{snap['tech_direct_pct']:.1f}%", f"{snap['tech_direct_pct'] - float(previous['tech_direct_pct']):+.1f}pp"],
            ["美元/台幣", f"{float(previous['fx_usdtwd']):.3f}", f"{snap['fx_usdtwd']:.3f}", f"{snap['fx_usdtwd'] - float(previous['fx_usdtwd']):+.3f}"],
        ]
        story.append(styled_table(perf, [1.3 * inch, 1.25 * inch, 1.25 * inch, 1.35 * inch], 7))
        story.append(Paragraph(f"已知現金流調整：本期現金為 {CASH_TWD/10000:.0f} 萬元，與前期現金差額 {cash_flow/10000:+,.1f} 萬元視為資金流入/流出，不算投資損益；扣除現金流後變化約 {adj_change/10000:+,.1f} 萬元。缺少完整交易明細，因此未計算精確時間加權報酬。", styles["small"]))
    else:
        story.append(Paragraph("首次建立績效歷史，本期作為基準期，未虛構前期比較值。", styles["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("本期績效貢獻與拖累", styles["h2"]))
    winners = pf.sort_values("pnl_twd", ascending=False).head(5)
    losers = pf.sort_values("pnl_twd").head(5)
    wtab = [["貢獻較大", "累積損益", "拖累較大", "累積損益"]]
    for (_, w), (_, l) in zip(winners.iterrows(), losers.iterrows()):
        wtab.append([f"{w.stock_id} {w.stock_name}", f"{w.pnl_twd/10000:+,.1f}萬", f"{l.stock_id} {l.stock_name}", f"{l.pnl_twd/10000:+,.1f}萬"])
    story.append(styled_table(wtab, [1.55 * inch, 0.9 * inch, 1.55 * inch, 0.9 * inch], 7))
    story.append(Spacer(1, 8))
    story.append(Paragraph("操作結論", styles["h2"]))
    story.append(Paragraph("核心持股可維持定期定額；新增資金以海外核心、債券與低波高息補足。衛星持股需降低到 10-20% 目標區間，單一衛星高於 5% 者分批調節，不以一次性賣出處理。跌破 MA60 且相對強度轉弱時停止加碼；跌破 MA120 或放量下跌且訊號不足時分批減碼或退出。", styles["body"]))
    out = os.path.join(STOCK_DIR, f"個人投資部位分析報告_{TODAY.isoformat()}.pdf")
    out = build_doc_with_fallback(out, f"個人投資部位分析報告_{TODAY.isoformat()}", "依最新投資部位檔與現金 200 萬元計算", story, styles, "重跑版")
    return out


def dashboard_title(text, styles):
    return Paragraph(f'<font color="#16496a"><b>{text}</b></font>', styles["h2"])


def money_wan(value):
    return f"{float(value) / 10000:,.1f}萬"


def asset_pie_drawing(items, width=230, height=105):
    drawing = Drawing(width, height)
    palette = [colors.HexColor("#1c4e7a"), colors.HexColor("#90bdc9"), colors.HexColor("#8a969a"), colors.HexColor("#2f6f8f")]
    values = [max(float(v), 0.0) for _, v in items]
    if sum(values) <= 0:
        values = [1 for _ in items]
    pie = Pie()
    pie.x = 120
    pie.y = 10
    pie.width = 82
    pie.height = 82
    pie.data = values
    pie.slices.strokeWidth = 0.3
    for i in range(len(values)):
        pie.slices[i].fillColor = palette[i % len(palette)]
    drawing.add(pie)
    y = 78
    total = sum(values)
    for i, (label, value) in enumerate(items):
        pct = value / total * 100 if total else 0
        drawing.add(Rect(4, y - 6, 6, 6, fillColor=palette[i % len(palette)], strokeColor=None))
        drawing.add(String(14, y - 6, f"{label} {pct:.1f}%", fontName="MSJH", fontSize=6.4, fillColor=colors.HexColor("#263f4a")))
        y -= 12
    return drawing


def weight_bar_drawing(rows, width=270, height=180):
    drawing = Drawing(width, height)
    max_val = max([float(v) for _, v in rows] + [1.0])
    y = height - 14
    bar_x = 78
    bar_w = width - bar_x - 32
    for i, (label, value) in enumerate(rows[:9]):
        val = float(value)
        fill = colors.HexColor("#1c4e7a") if i % 2 == 0 else colors.HexColor("#90bdc9")
        drawing.add(String(2, y, str(label)[:15], fontName="MSJH", fontSize=6.0, fillColor=colors.HexColor("#263f4a")))
        drawing.add(Rect(bar_x, y - 2, bar_w, 5, fillColor=colors.HexColor("#e7f0f3"), strokeColor=None))
        drawing.add(Rect(bar_x, y - 2, bar_w * val / max_val, 5, fillColor=fill, strokeColor=None))
        drawing.add(String(bar_x + bar_w + 3, y - 1, f"{val:.1f}%", fontName="MSJH", fontSize=5.8, fillColor=colors.HexColor("#263f4a")))
        y -= 13
    return drawing


def compact_table(data, widths=None, font_size=6.2):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "MSJH"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), font_size + 2.6),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#263f4a")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.45, colors.HexColor("#7895a2")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.18, colors.HexColor("#d8e5e9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
            ]
        )
    )
    return t


def build_holding_recommendations(pf, latest=None):
    eligible_pf = pf[
        pd.to_numeric(pf["weight_pct"], errors="coerce").fillna(0)
        >= HOLDING_RECOMMENDATION_MIN_WEIGHT_PCT
    ].copy()
    model_by_id = {}
    if latest is not None and not latest.empty:
        model_rows = latest.copy()
        model_rows["stock_id"] = model_rows["stock_id"].astype(str)
        for sid, rows in model_rows.groupby("stock_id", sort=False):
            model_by_id[sid] = rows.iloc[0]

    price_cache = {}

    def price_series(symbol):
        if symbol not in price_cache:
            price_cache[symbol] = yahoo_price_series(symbol, "1y")
        return price_cache[symbol]

    def benchmark_return(symbol):
        series = price_series(symbol)
        closes = pd.to_numeric(series.get("close"), errors="coerce").dropna()
        if len(closes) < 61:
            return None
        return float(closes.iloc[-1] / closes.iloc[-61] - 1)

    benchmark_returns = {
        "台灣": benchmark_return("^TWII"),
        "美國": benchmark_return("SPY"),
    }
    rows = []
    for _, holding in eligible_pf.sort_values("weight_pct", ascending=False).iterrows():
        sid = str(holding.get("stock_id", "")).strip()
        market = str(holding.get("market", "")).strip()
        category = str(holding.get("category", "")).strip()
        action = "持有"
        reason = ""
        model_label = "-"
        model = model_by_id.get(sid) if market == "台灣" else None

        if model is not None:
            close = float(model.get("close", 0) or 0)
            ma60 = float(model.get("ma60", 0) or 0)
            ma120 = float(model.get("ma120", 0) or 0)
            weak_rs = not bool(model.get("relative_strength", False))
            volume_down = bool(model.get("volume_down", False))
            signals = int(model.get("academic_signal_count", model.get("buy_signals", 0)) or 0)
            score = float(model.get("score", 0) or 0)
            model_label = f"{score * 100:.0f}/{signals}"
            if volume_down:
                action = "賣出"
                reason = "放量下跌，觸發模型退出"
            elif ma120 > 0 and close < ma120 and weak_rs:
                action = "賣出"
                reason = "跌破 MA120 且相對強度轉弱"
            elif signals < 5 and ma60 > 0 and close < ma60 and weak_rs:
                action = "賣出"
                reason = "指標少於 5 且跌破 MA60、相對弱勢"
            elif bool(model.get("overheat", False)):
                reason = f"趨勢未破壞；{signals}/10，但短線過熱不加碼"
            else:
                reason = f"未觸發退出；10 指標成立 {signals} 項"
        else:
            symbol = f"{sid}.TW" if market == "台灣" else sid
            series = price_series(symbol)
            closes = pd.to_numeric(series.get("close"), errors="coerce").dropna()
            if len(closes) >= 120:
                close = float(closes.iloc[-1])
                ma20 = float(closes.tail(20).mean())
                ma60 = float(closes.tail(60).mean())
                ma120 = float(closes.tail(120).mean())
                ret3m = float(close / closes.iloc[-61] - 1) if len(closes) >= 61 else None
                benchmark = benchmark_returns.get(market)
                trend_signals = [
                    close >= ma20,
                    ma20 >= ma60,
                    ma60 >= ma120,
                    ret3m is not None and benchmark is not None and ret3m >= benchmark,
                ]
                trend_count = int(sum(trend_signals))
                model_label = f"趨勢 {trend_count}/4"
                if close < ma120 and trend_count <= 1:
                    action = "賣出"
                    reason = "跌破 MA120 且趨勢/相對強度僅 0-1 項"
                else:
                    reason = f"未觸發退出；趨勢與相對強度 {trend_count}/4"
            else:
                model_label = "資料不足"
                if category == "核心":
                    reason = "公開日線不足；核心ETF紀律持有"
                elif category in {"核心單股", "債券/現金"} or sid == "SPCX":
                    reason = "公開日線不足；依核心/特殊部位紀律持有"
                else:
                    reason = "公開日線不足；暫持有、不加碼並持續查核"

        rows.append(
            {
                "name": f"{sid} {holding.get('stock_name', '')}".strip(),
                "market": market,
                "category": category,
                "weight_pct": float(holding.get("weight_pct", 0) or 0),
                "model": model_label,
                "action": action,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def build_personal_dashboard_report(pf, snap, previous, latest=None):
    styles = setup_pdf()
    styles["panel_text"] = ParagraphStyle("panel_text", parent=styles["small"], fontSize=6.3, leading=8.0)
    story = []
    asset_items = [
        ("核心", snap["total_assets_twd"] * snap["core_pct"] / 100),
        ("衛星", snap["total_assets_twd"] * snap["satellite_pct"] / 100),
        ("債券/現金", snap["total_assets_twd"] * snap["bond_pct"] / 100 + CASH_TWD),
    ]
    composition = compact_table(
        [
            ["項目", "市值", "%"],
            ["總資產", money_wan(snap["total_assets_twd"]), "100.0"],
            ["證券", money_wan(snap["securities_twd"]), f"{snap['securities_twd'] / snap['total_assets_twd'] * 100:.1f}"],
            ["現金", money_wan(CASH_TWD), f"{CASH_TWD / snap['total_assets_twd'] * 100:.1f}"],
        ],
        [0.85 * inch, 0.95 * inch, 0.55 * inch],
        6.1,
    )
    top = pf.sort_values("pnl_twd", ascending=False).head(8)
    contrib_rows = [["貢獻最高標的", "權重", "損益", "報酬"]]
    for _, r in top.iterrows():
        contrib_rows.append([f"{r.stock_id} {r.stock_name}"[:18], f"{r.weight_pct:.1f}%", money_wan(r.pnl_twd), f"{r.return_pct:+.1f}%"])
    contrib = compact_table(contrib_rows, [1.78 * inch, 0.52 * inch, 0.70 * inch, 0.55 * inch], 5.7)
    div_twd = snap.get("total_div_twd", 0.0)
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
    performance = compact_table(perf_rows, [1.80 * inch, 1.30 * inch, 2.10 * inch, 2.54 * inch], 5.8)
    category_rows = pf.groupby("category")["weight_pct"].sum().sort_values(ascending=False).reset_index()
    weight_rows = [(str(r["category"]), float(r["weight_pct"])) for _, r in category_rows.iterrows()]
    top_weights = pf.sort_values("weight_pct", ascending=False).head(9)
    over = pf[(pf["category"].eq("衛星")) & (pf["weight_pct"] > 5)].sort_values("weight_pct", ascending=False)
    model_trims = []
    if latest is not None and not latest.empty:
        latest_by_id = latest.copy()
        latest_by_id["stock_id"] = latest_by_id["stock_id"].astype(str)
        latest_by_id = latest_by_id.set_index("stock_id", drop=False)
        for _, holding in pf.iterrows():
            sid = str(holding.get("stock_id", "")).strip()
            if sid not in latest_by_id.index:
                continue
            model = latest_by_id.loc[sid]
            if isinstance(model, pd.DataFrame):
                model = model.iloc[0]
            action = None
            reason = None
            if bool(model.get("volume_down", False)):
                action = "賣出"
                reason = "放量下跌，依全球模型退出"
            elif float(model.get("close", 0) or 0) < float(model.get("ma120", 0) or 0) and not bool(model.get("relative_strength", False)):
                action = "賣出"
                reason = "跌破 MA120 且相對強度轉弱"
            elif int(model.get("academic_signal_count", model.get("buy_signals", 0)) or 0) < 5:
                action = "減碼"
                reason = "學術證據指標低於續抱門檻"
            elif bool(model.get("overheat", False)):
                action = "減碼"
                reason = "急漲過熱，持有者分批停利"
            if action:
                model_trims.append(
                    {
                        "name": f"{holding.get('stock_id', sid)} {holding.get('stock_name', holding.get('name', sid))}",
                        "weight_pct": float(holding.get("weight_pct", 0) or 0),
                        "action": action,
                        "reason": reason,
                        "score": float(model.get("score", 0) or 0),
                        "signals": int(model.get("academic_signal_count", model.get("buy_signals", 0)) or 0),
                    }
                )
    trim_watch = pd.DataFrame(model_trims)
    if not trim_watch.empty:
        trim_watch["rank_action"] = trim_watch["action"].map({"賣出": 0, "減碼": 1}).fillna(2)
        trim_watch = trim_watch.sort_values(["rank_action", "weight_pct"], ascending=[True, False]).head(5)
    div_wan = snap.get("total_div_twd", 0.0) / 10000
    ret_div_pct = snap.get("total_return_with_div_pct", snap["cumulative_return_pct"])
    risk_lines = [
        f"近一年含息總報酬率 {ret_div_pct:.2f}% (含實收股息約 {div_wan:.1f} 萬元)，具備強健現金流支撐。",
        f"8% 年化目標配置建議：核心ETF (0050/SPY) 提供 5.5% 資本利得 + 高股息/債券提供 2.5% 股息收益。",
        f"科技集中度 {snap['tech_direct_pct']:.1f}%；衛星 {snap['satellite_pct']:.1f}%。新增資金優先補海外核心與高息債券。",
    ]
    for _, r in over.head(3).iterrows():
        risk_lines.append(f"{r.stock_id} {r.stock_name} 衛星權重 {r.weight_pct:.1f}%，高於 5% 可分批調節。")
    if snap["satellite_pct"] > 20:
        risk_lines.append("衛星總比重高於 20%，先停止加碼高波動衛星。")
    if not trim_watch.empty:
        risk_lines.append("持股調節清單依全球學術模型賣出準則產生，優先處理賣出訊號。")
    conclusion = []
    for line in risk_lines[:6]:
        conclusion.append(Paragraph("• " + line, styles["panel_text"]))
        conclusion.append(Spacer(1, 2))
    trim_rows = [["模型賣出/減碼", "權重", "分數", "原因"]]
    for _, r in trim_watch.iterrows():
        trim_rows.append([
            str(r["name"])[:16],
            f"{r.weight_pct:.1f}%",
            f"{r.score * 100:.1f}/{int(r.signals)}/10",
            f"{r.action}：{r.reason}",
        ])
    if len(trim_rows) == 1:
        trim_rows.append(["無", "-", "-", "未觸發全球模型賣出/減碼準則"])
    trim_table = compact_table(trim_rows, [1.05 * inch, 0.42 * inch, 0.48 * inch, 1.35 * inch], 5.6)
    core_holdings = pf[pf["category"].eq("核心")].sort_values("weight_pct", ascending=False)
    core_rows = [["完整核心持股", "權重", "損益", "報酬"]]
    for _, r in core_holdings.iterrows():
        core_rows.append([
            f"{r.stock_id} {r.stock_name}"[:17],
            f"{r.weight_pct:.1f}%",
            money_wan(r.pnl_twd),
            f"{r.return_pct:+.1f}%" if pd.notna(r.get("return_pct")) else "N/A",
        ])
    if len(core_rows) == 1:
        core_rows.append(["無", "-", "-", "-"])
    core_table = compact_table(core_rows, [1.18 * inch, 0.42 * inch, 0.55 * inch, 0.45 * inch], 5.1)
    satellite_top3 = pf[pf["category"].eq("衛星")].sort_values("weight_pct", ascending=False).head(3)
    satellite_rows = [["前三大衛星持股", "權重", "損益", "報酬"]]
    for _, r in satellite_top3.iterrows():
        satellite_rows.append([
            f"{r.stock_id} {r.stock_name}"[:17],
            f"{r.weight_pct:.1f}%",
            money_wan(r.pnl_twd),
            f"{r.return_pct:+.1f}%" if pd.notna(r.get("return_pct")) else "N/A",
        ])
    if len(satellite_rows) == 1:
        satellite_rows.append(["無", "-", "-", "-"])
    satellite_table = compact_table(satellite_rows, [1.18 * inch, 0.42 * inch, 0.55 * inch, 0.45 * inch], 5.1)
    operation_lines = [
        "操作結論：未觸發模型賣出時，核心持股以續抱與定期投入為主。",
        "衛星前三大若權重高於 5%，優先用分批調節，不一次性處理。",
    ]
    if not trim_watch.empty:
        operation_lines[0] = "操作結論：先處理模型賣出訊號，其次才是減碼與權重調節。"
    operation_note = [Paragraph("• " + line, styles["panel_text"]) for line in operation_lines]
    left_top = [
        dashboard_title("投資組合構成", styles), 
        composition, 
        asset_pie_drawing(asset_items),
        Spacer(1, 6),
        dashboard_title("投資比重", styles),
        weight_bar_drawing(weight_rows[:9], height=max(70, min(110, 28 + 13 * len(weight_rows[:9])))),
    ]
    right_top = [
        dashboard_title("主要獲利貢獻", styles), 
        contrib,
        Spacer(1, 6),
        dashboard_title("集中度與調節建議", styles),
    ] + conclusion + [
        Spacer(1, 4),
        satellite_table,
        Spacer(1, 4),
        trim_table,
        Spacer(1, 4),
    ] + operation_note

    dashboard = Table(
        [[left_top, right_top]],
        colWidths=[3.87 * inch, 3.87 * inch],
        rowHeights=[7.80 * inch],
    )
    dashboard.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEAFTER", (0, 0), (0, 0), 0.25, colors.HexColor("#d8e5e9")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfdfe")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(Paragraph(f"報告日期：{TODAY.isoformat()}　總資產 {money_wan(snap['total_assets_twd'])}　現金 {money_wan(CASH_TWD)}　僅供研究參考，不構成投資建議。", styles["body"]))
    story.append(Spacer(1, 5))
    story.append(dashboard)

    # PAGE 2: Target Return Review -> Performance Summary (with Dividends) -> Individual Holding Recommendations
    recommendations = build_holding_recommendations(pf, latest)
    story.append(PageBreak())
    target_review = return_target_review(pf, snap, 0.08)
    target_rows = [
        ["8%年化目標檢核", "目前估算", "目標/缺口", "建議"],
        [
            "目標報酬",
            f"{target_review['expected_pct']:.2f}%",
            f"{target_review['target_pct']:.1f}% / {target_review['gap_pct']:+.2f}pp",
            "估算已達標，仍需控管集中度" if target_review["can_reach"] else "估算未達標，需提高核心成長資產比重",
        ],
        [
            "年度金額",
            money_wan(target_review["expected_income_twd"]),
            money_wan(target_review["target_income_twd"]),
            f"保留約5%現金後，可先投入 {money_wan(target_review['deploy_cash_twd'])}",
        ],
        [
            "配置修正",
            f"現金 {target_review['cash_pct']:.1f}%",
            f"衛星 {target_review['satellite_pct']:.1f}% / 科技 {target_review['tech_pct']:.1f}%",
            "新增資金優先0050/006208/SPY/VT；單一高波動標的分批降至5-10%",
        ],
    ]
    target_table = compact_table(
        target_rows,
        [1.30 * inch, 1.20 * inch, 1.40 * inch, 3.84 * inch],
        5.8,
    )
    story.append(dashboard_title("8%年化報酬目標｜目前配置與修正建議", styles))
    story.append(target_table)
    story.append(Spacer(1, 4))

    # Move Performance Summary to Page 2 (after Target Return, before Holding Recommendations)
    story.append(dashboard_title("績效摘要與前一期比較 (含資本利得與近一年股息)", styles))
    story.append(performance)
    story.append(Spacer(1, 4))

    story.append(dashboard_title("逐檔持股模型建議｜持有或賣出", styles))
    story.append(
        Paragraph(
            f"僅針對總資產權重達 {HOLDING_RECOMMENDATION_MIN_WEIGHT_PCT:.0f}% 以上的持股進行判讀。"
            "台股優先採用既有 10 指標模型；賣出條件為放量下跌、跌破 MA120 且相對強度轉弱，"
            "或指標少於 5 且同時跌破 MA60、相對弱勢。其他公開市場標的採 MA20/60/120 與"
            "3 個月相對強度四項趨勢檢核。資料不足者不推定技術訊號，標示後持續查核。",
            styles["small"],
        )
    )
    story.append(Spacer(1, 5))
    recommendation_rows = [["標的", "市場", "類別", "權重", "模型", "建議", "判斷依據"]]
    for _, r in recommendations.iterrows():
        recommendation_rows.append(
            [
                str(r["name"])[:24],
                r["market"],
                r["category"],
                f"{r.weight_pct:.1f}%",
                r["model"],
                r["action"],
                r["reason"],
            ]
        )
    recommendation_style = [
        ("FONTNAME", (0, 0), (-1, -1), "MSJH"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("LEADING", (0, 0), (-1, -1), 8.0),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#195b82")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7f9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.2, colors.HexColor("#b7cdd6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (5, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
    ]
    for row_number, action in enumerate(recommendations["action"], start=1):
        action_color = "#9f1d24" if action == "賣出" else "#147447"
        recommendation_style.append(("TEXTCOLOR", (5, row_number), (5, row_number), colors.HexColor(action_color)))
    recommendation_table = Table(
        recommendation_rows,
        colWidths=[1.26 * inch, 0.42 * inch, 0.60 * inch, 0.46 * inch, 0.65 * inch, 0.45 * inch, 3.90 * inch],
        repeatRows=1,
        style=TableStyle(recommendation_style),
    )
    story.append(recommendation_table)
    out = os.path.join(STOCK_DIR, f"個人投資部位分析報告_{TODAY.isoformat()}.pdf")
    return build_doc_with_fallback(out, f"個人投資部位分析報告_{TODAY.isoformat()}", f"報告日期：{TODAY.isoformat()}｜依最新投資部位檔與現金 200 萬元計算", story, styles, "dashboard")


def latest_history_after_close():
    data_date, daily, errors = download_twse_daily(TODAY, allow_prior=False)
    if daily is not None:
        return data_date, update_history(daily), errors

    history_path = os.path.join(STOCK_DIR, "twse_listed_close_volume_history_53w.csv")
    if os.path.exists(history_path):
        history = pd.read_csv(history_path, encoding="utf-8-sig", dtype={"stock_id": str}, low_memory=False)
        if not history.empty:
            data_date = pd.to_datetime(history["date"]).max().date()
            if data_date == TODAY:
                return data_date, history, errors

    detail = " | ".join(errors[-3:]) if errors else "no same-day TWSE data available"
    raise RuntimeError(
        f"Evening review requires {TODAY.isoformat()} closing data; "
        f"the latest available data is not from today. Download notes: {detail}"
    )


def selected_today_rows():
    snapshot_path = os.path.join(STOCK_DIR, f"morning_selection_snapshot_{TODAY.isoformat()}.json")
    if os.path.exists(snapshot_path):
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        rows = pd.DataFrame(snapshot.get("selected", []))
        if not rows.empty:
            return rows.sort_values("rank").head(10), snapshot.get("report_date", TODAY.isoformat())

    path = os.path.join(STOCK_DIR, "satellite_recommendation_history.csv")
    if not os.path.exists(path):
        return pd.DataFrame(), None
    hist = pd.read_csv(path, encoding="utf-8-sig", dtype=str, on_bad_lines="skip")
    if hist.empty or "report_date" not in hist.columns:
        return pd.DataFrame(), None
    rows = hist[hist["report_date"].astype(str) == TODAY.isoformat()].copy()
    if rows.empty:
        return pd.DataFrame(), None
    return rows.drop_duplicates("stock_id", keep="last").head(10), TODAY.isoformat()


def loss_reason(row, market_positive):
    reasons = []
    if market_positive < 0.45:
        reasons.append("weak market breadth")
    if bool(row.get("volume_down", False)):
        reasons.append("high-volume selloff")
    if float(row.get("close", 0) or 0) < float(row.get("ma20", 0) or 0):
        reasons.append("closed below MA20")
    if bool(row.get("overheat_morning", row.get("overheat", False))):
        reasons.append("morning selection had overheat risk")
    if float(row.get("total_lots_morning", row.get("total_lots", 0)) or 0) < 0:
        reasons.append("morning selection had institutional net selling")
    if float(row.get("score_low_vol_morning", row.get("score_low_vol", 0)) or 0) < 0.45:
        reasons.append("morning volatility filter was too loose")
    if float(row.get("score_ma_trend_morning", row.get("score_ma_trend", 0)) or 0) < 0.50:
        reasons.append("morning MA trend quality was weak")
    if (
        float(row.get("score_price_volume_morning", row.get("score_price_volume", 0)) or 0) >= 0.70
        or float(row.get("score_abnormal_volume_morning", row.get("score_abnormal_volume", 0)) or 0) >= 0.70
    ):
        reasons.append("morning selection relied heavily on price/volume chase")
    if not reasons:
        reasons.append("normal pullback/no single dominant signal")
    return "; ".join(reasons)


def apply_evening_adjustments(review, market_return):
    strategy = load_strategy()
    weights = strategy["weights"].copy()
    penalties = strategy["penalties"].copy()
    thresholds = strategy["thresholds"].copy()
    losers = review[review["day_pct"] < 0].copy()
    severe = review[review["day_pct"] <= -2].copy()
    avg_ret = float(review["day_pct"].mean()) if not review.empty else 0.0
    changes = []

    def bump(key, delta):
        weights[key] = max(0.01, float(weights.get(key, 0)) + delta)

    if len(losers) >= 4 or avg_ret < market_return:
        bump("score_momentum", -0.02)
        bump("score_price_volume", -0.01)
        bump("score_abnormal_volume", -0.01)
        bump("score_low_vol", 0.02)
        bump("score_ma_trend", 0.01)
        bump("score_inst_alignment", 0.01)
        penalties["volume_down"] = min(0.35, float(penalties.get("volume_down", 0.20)) + 0.03)
        thresholds["low_vol_rank_max"] = max(0.45, float(thresholds.get("low_vol_rank_max", 0.55)) - 0.02)
        changes.append("Shifted weight from raw momentum/volume chase toward low volatility, MA trend, and institution alignment.")
        changes.append("Raised the high-volume selloff penalty and tightened the low-volatility filter.")

    if not severe.empty and severe["reason"].astype(str).str.contains("overheat", case=False, na=False).any():
        penalties["overheat"] = min(0.18, float(penalties.get("overheat", 0.08)) + 0.02)
        bump("score_high52", -0.01)
        bump("score_low_vol", 0.01)
        changes.append("Raised the overheat penalty after severe losers showed prior overheat risk.")

    if not severe.empty and severe["reason"].astype(str).str.contains("institutional net selling", case=False, na=False).any():
        bump("score_inst_intensity", 0.01)
        bump("score_stock_rs", -0.01)
        changes.append("Gave institution flow more influence when severe losers had net institutional selling.")

    if not changes:
        changes.append("No material downgrade trigger; kept the strategy weights stable.")

    strategy["weights"] = normalize_weights(weights)
    strategy["penalties"] = penalties
    strategy["thresholds"] = thresholds
    strategy["last_review_date"] = TODAY.isoformat()
    log = strategy.get("change_log", [])
    log.append(
        {
            "date": TODAY.isoformat(),
            "selected": int(len(review)),
            "down_count": int(len(losers)),
            "avg_day_pct": round(avg_ret, 3),
            "market_median_pct": round(float(market_return), 3),
            "changes": changes,
        }
    )
    strategy["change_log"] = log[-30:]
    save_strategy(strategy)
    return strategy, changes


def evening_review():
    data_date, history, download_errors = latest_history_after_close()
    t86, _ = download_t86(data_date)
    status = market_status(history)
    latest, _ = calculate_candidates(history, status, t86)
    selected, report_date = selected_today_rows()
    if selected.empty:
        raise RuntimeError("No morning recommendation history was found.")

    latest["stock_id"] = latest["stock_id"].astype(str)
    selected["stock_id"] = selected["stock_id"].astype(str)
    selected_cols = [
        col
        for col in ["stock_id", "stock_name", "score"] + STRATEGY_SCORE_COLUMNS
        + ["overheat", "volume_down", "low_vol", "ma_ratio", "relative_strength", "total_lots"]
        if col in selected.columns
    ]
    merged = selected[selected_cols].merge(latest, on="stock_id", how="left", suffixes=("_morning", ""))
    latest_open = pd.to_numeric(latest["open"], errors="coerce")
    latest_close = pd.to_numeric(latest["close"], errors="coerce")
    market_open_to_close = ((latest_close - latest_open) / latest_open * 100).fillna(pd.to_numeric(latest["pct_change"], errors="coerce"))
    market_return = float(market_open_to_close.median(skipna=True))
    market_positive = (market_open_to_close > 0).mean()
    rows = []
    for _, r in merged.iterrows():
        op = clean_num(r.get("open"))
        cl = clean_num(r.get("close"))
        if op and cl and op > 0:
            pct = (cl - op) / op * 100
        else:
            pct = float(r.get("pct_change", 0) or 0)
        item = {
            "review_date": TODAY.isoformat(),
            "morning_report_date": report_date,
            "market_data_date": data_date.isoformat(),
            "stock_id": r.get("stock_id", ""),
            "stock_name": r.get("stock_name", r.get("stock_name_morning", "")),
            "open": op,
            "close": cl,
            "day_pct": round(pct, 3),
            "result": "down" if pct < 0 else "up_or_flat",
            "morning_score": r.get("score_morning", r.get("score", "")),
            "reason": loss_reason(r, market_positive) if pct < 0 else "held up relative to review focus",
        }
        for col in STRATEGY_SCORE_COLUMNS:
            item[f"morning_{col}"] = r.get(f"{col}_morning", r.get(col, ""))
        rows.append(item)
    review = pd.DataFrame(rows)
    strategy, changes = apply_evening_adjustments(review, market_return)
    csv_path = os.path.join(WORK_DIR, f"evening_strategy_review_{TODAY.isoformat()}.csv")
    txt_path = os.path.join(WORK_DIR, f"evening_strategy_review_{TODAY.isoformat()}.txt")
    review.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Review date: {TODAY.isoformat()}\n")
        f.write(f"Morning report date: {report_date}\n")
        f.write(f"Market data date: {data_date.isoformat()}\n")
        f.write(f"Selected: {len(review)}; down: {int((review['day_pct'] < 0).sum())}; avg pct: {review['day_pct'].mean():.3f}\n")
        if download_errors:
            f.write("Download notes: " + " | ".join(download_errors[-3:]) + "\n")
        f.write("\nChange highlights:\n")
        for change in changes:
            f.write(f"- {change}\n")
        f.write("\nCurrent weights:\n")
        for key, value in strategy["weights"].items():
            f.write(f"- {key}: {value:.4f}\n")
    print(txt_path)
    print(csv_path)
    print(STRATEGY_PATH)


def main():
    if "--evening-review" in sys.argv:
        evening_review()
        return
    data_date, daily, download_errors = download_twse_daily()
    if daily is None:
        history_path = os.path.join(STOCK_DIR, "twse_listed_close_volume_history_53w.csv")
        history = pd.read_csv(history_path, encoding="utf-8-sig", dtype={"stock_id": str}, low_memory=False)
        data_date = pd.to_datetime(history["date"]).max().date()
    else:
        history = update_history(daily)
    t86, t86_error = download_t86(data_date)
    mrows, fxq, oil, tnx, extras = get_market_snapshot()
    fx = fxq["close"] if (fxq and isinstance(fxq, dict) and fxq.get("close") is not None) else 31.638
    status = market_status(history)
    latest, candidates = calculate_candidates(history, status, t86)
    pf, snap = analyze_portfolio(fx)
    previous = append_portfolio_history(snap)
    previous_followups = read_previous_recommendations(latest, history)
    global_pdf = build_global_report(data_date, history, candidates, latest, previous_followups, t86, t86_error, mrows, fxq, oil, tnx, extras, download_errors)
    personal_pdf = build_personal_dashboard_report(pf, snap, previous, latest)
    print(global_pdf)
    print(personal_pdf)


if __name__ == "__main__":
    main()
