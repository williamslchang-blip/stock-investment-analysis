"""平日投資報告與晚間複盤的排程入口。"""

from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import shutil
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "programs" / "generate_daily_investment_reports.py"
POSITION_DIR = ROOT / "投資部位"
CONFIG = ROOT / "config" / "strategy_adjustments.json"
LOG_DIR = ROOT / "logs"
REVIEW_DIR = ROOT / "results" / "evening_review"
INVALID_DIR = ROOT / "qa" / "invalid_outputs"
TODAY = date.today()


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunLog:
    def __init__(self, mode: str):
        self.mode = mode
        self.lines: list[str] = []
        self.started = datetime.now()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOG_DIR / f"{mode}_{self.started:%Y-%m-%d_%H%M%S}.log"

    def add(self, message: str) -> None:
        line = f"[{now_text()}] {message}"
        self.lines.append(line)
        print(line, flush=True)

    def save(self, status: str) -> None:
        self.add(f"執行狀態：{status}")
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8-sig")


def load_generator():
    if not PROGRAM.exists():
        raise FileNotFoundError(f"找不到產報主程式：{PROGRAM}")
    spec = importlib.util.spec_from_file_location("daily_report_generator", PROGRAM)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入產報主程式：{PROGRAM}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.STOCK_DIR = str(ROOT)
    module.POSITION_DIR = str(POSITION_DIR)
    module.WORK_DIR = str(REVIEW_DIR)
    module.STRATEGY_PATH = str(CONFIG)
    return module


def validate_positions() -> None:
    for name in ("DP.csv", "IP.csv"):
        path = POSITION_DIR / name
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError(f"找不到最新部位檔或檔案為空：{path}")
        try:
            rows = path.read_text(encoding="cp950").splitlines()
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"{name} 不是預期的 CP950／Big5 編碼：{exc}") from exc
        if len([row for row in rows if row.strip()]) < 2:
            raise RuntimeError(f"{name} 沒有可用的部位資料列")


def pdf_pages(path: Path) -> int:
    if not path.exists() or path.stat().st_size < 10_000:
        return 0
    return len(PdfReader(str(path)).pages)


def archive_invalid(path: Path, log: RunLog) -> None:
    if not path.exists():
        return
    INVALID_DIR.mkdir(parents=True, exist_ok=True)
    target = INVALID_DIR / f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
    shutil.move(str(path), str(target))
    log.add(f"保留無效輸出供查核：{target}")


def assert_history_unique() -> None:
    path = ROOT / "portfolio_performance_history.csv"
    if not path.exists():
        raise FileNotFoundError(f"找不到績效歷史：{path}")
    hist = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    if "date" not in hist.columns:
        raise RuntimeError("績效歷史缺少 date 欄位")
    duplicates = hist.loc[hist["date"].duplicated(keep=False), "date"].dropna().unique().tolist()
    if duplicates:
        raise RuntimeError(f"績效歷史出現同日重複：{', '.join(duplicates)}")


def run_morning(log: RunLog) -> None:
    validate_positions()
    expected = {
        ROOT / f"全球投資市場研究報告_{TODAY.isoformat()}.pdf": 2,
        ROOT / f"個人投資部位分析報告_{TODAY.isoformat()}.pdf": 2,
    }
    for path, pages in expected.items():
        if path.exists() and pdf_pages(path) != pages:
            archive_invalid(path, log)

    module = load_generator()
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        module.main()
    output = captured.getvalue().strip()
    if output:
        for line in output.splitlines():
            log.add(f"主程式：{line}")

    failures = [
        f"{path.name} 預期 {pages} 頁，實際 {pdf_pages(path)} 頁"
        for path, pages in expected.items()
        if pdf_pages(path) != pages
    ]
    if failures:
        raise RuntimeError("；".join(failures))
    assert_history_unique()
    log.add("全球報告 2 頁、個人 dashboard 2 頁，且績效歷史同日無重複。")


def load_morning_snapshot() -> tuple[pd.DataFrame, dict]:
    path = ROOT / f"morning_selection_snapshot_{TODAY.isoformat()}.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到今日上午選股快照：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected = pd.DataFrame(payload.get("selected", []))
    if selected.empty:
        raise RuntimeError("今日上午選股快照沒有候選股票，無法進行績效複盤")
    return selected, payload


def review_recommendation(history: pd.DataFrame, today: pd.DataFrame) -> tuple[str, str]:
    dates = sorted(history["複盤日期"].astype(str).dropna().unique()) if not history.empty else []
    relative = float(today["相對市場報酬率"].mean()) if not today.empty else 0.0
    down_ratio = float((today["當日報酬率"] < 0).mean()) if not today.empty else 0.0
    if len(dates) < 20:
        return (
            "維持現行策略",
            f"目前只有 {len(dates)} 個交易日的正式複盤，未達 20 日最低評估窗；"
            f"今日平均相對市場 {relative:+.2f}%，下跌比率 {down_ratio:.0%}。單日結果不調整權重。",
        )
    recent_dates = dates[-20:]
    sample = history[history["複盤日期"].astype(str).isin(recent_dates)].copy()
    avg_relative = float(pd.to_numeric(sample["相對市場報酬率"], errors="coerce").mean())
    hit_rate = float((pd.to_numeric(sample["相對市場報酬率"], errors="coerce") > 0).mean())
    if avg_relative <= -0.5 and hit_rate < 0.45:
        return (
            "建議進行離線再估計",
            f"最近 20 日平均相對市場 {avg_relative:+.2f}%，勝率 {hit_rate:.0%}；"
            "建議用獨立驗證期間重估權重，通過回測與前視偏誤檢查後才上線。",
        )
    return (
        "維持現行策略",
        f"最近 20 日平均相對市場 {avg_relative:+.2f}%，勝率 {hit_rate:.0%}，"
        "尚未同時觸發績效與勝率門檻。",
    )


def run_evening(log: RunLog) -> None:
    module = load_generator()
    selected, payload = load_morning_snapshot()
    data_date, daily, errors = module.download_twse_daily(TODAY, allow_prior=False)
    if daily is None or data_date != TODAY:
        detail = "｜".join(errors[-3:]) if errors else "TWSE 尚未提供當日收盤資料"
        raise RuntimeError(f"晚間複盤需要 {TODAY.isoformat()} 收盤資料；{detail}")
    history = module.update_history(daily)
    t86, t86_error = module.download_t86(data_date)
    status = module.market_status(history)
    latest, _ = module.calculate_candidates(history, status, t86)

    selected["stock_id"] = selected["stock_id"].astype(str)
    latest["stock_id"] = latest["stock_id"].astype(str)
    current = selected.merge(
        latest[["stock_id", "stock_name", "open", "close", "pct_change", "ma20", "ma120", "total_lots"]],
        on="stock_id",
        how="left",
        suffixes=("_上午", ""),
    )
    current["開盤價"] = pd.to_numeric(current["open"], errors="coerce")
    current["收盤價"] = pd.to_numeric(current["close"], errors="coerce")
    
    # 計算開盤至收盤報酬率 ( (收盤價 - 開盤價) / 開盤價 )
    latest_open = pd.to_numeric(latest["open"], errors="coerce")
    latest_close = pd.to_numeric(latest["close"], errors="coerce")
    market_open_to_close = ((latest_close - latest_open) / latest_open * 100).fillna(pd.to_numeric(latest["pct_change"], errors="coerce"))
    market_return = float(market_open_to_close.median(skipna=True))
    
    current["當日報酬率"] = (((current["收盤價"] - current["開盤價"]) / current["開盤價"]) * 100).round(3)
    mask_fallback = current["開盤價"].isna() | (current["開盤價"] <= 0) | current["當日報酬率"].isna()
    current.loc[mask_fallback, "當日報酬率"] = pd.to_numeric(current.loc[mask_fallback, "pct_change"], errors="coerce")
    current["相對市場報酬率"] = current["當日報酬率"] - market_return
    current["複盤日期"] = TODAY.isoformat()
    current["上午資料日期"] = payload.get("recommendation_data_date", "")
    current["股票代號"] = current["stock_id"]
    current["股票名稱"] = current["stock_name"].fillna(current.get("stock_name_上午", ""))
    current["上午排名"] = pd.to_numeric(current.get("rank"), errors="coerce")
    current["上午分數"] = pd.to_numeric(current.get("score"), errors="coerce")
    current["法人買賣超張數"] = pd.to_numeric(current["total_lots"], errors="coerce")

    def finding(row) -> str:
        notes = []
        if pd.notna(row["當日報酬率"]) and row["當日報酬率"] < 0:
            notes.append("開盤至收盤下跌")
        if pd.notna(row["相對市場報酬率"]) and row["相對市場報酬率"] < 0:
            notes.append("落後市場中位數")
        if pd.notna(row["ma20"]) and pd.notna(row["收盤價"]) and row["收盤價"] < row["ma20"]:
            notes.append("跌破 MA20")
        if pd.notna(row["ma120"]) and pd.notna(row["收盤價"]) and row["收盤價"] < row["ma120"]:
            notes.append("跌破 MA120")
        if pd.notna(row["法人買賣超張數"]) and row["法人買賣超張數"] < 0:
            notes.append("三大法人賣超")
        return "、".join(notes) if notes else "未見主要轉弱訊號"

    current["複盤發現"] = current.apply(finding, axis=1)
    columns = [
        "複盤日期",
        "上午資料日期",
        "股票代號",
        "股票名稱",
        "上午排名",
        "上午分數",
        "開盤價",
        "收盤價",
        "當日報酬率",
        "相對市場報酬率",
        "法人買賣超張數",
        "複盤發現",
    ]
    result = current[columns].sort_values("上午排名")
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = REVIEW_DIR / f"晚間策略複盤_{TODAY.isoformat()}.csv"
    result.to_csv(daily_path, index=False, encoding="utf-8-sig")

    history_path = REVIEW_DIR / "晚間策略複盤歷史.csv"
    if history_path.exists():
        review_history = pd.read_csv(history_path, encoding="utf-8-sig", dtype={"股票代號": str})
    else:
        review_history = pd.DataFrame(columns=columns)
    review_history = pd.concat([review_history, result], ignore_index=True)
    review_history = review_history.drop_duplicates(["複盤日期", "股票代號"], keep="last")
    review_history.to_csv(history_path, index=False, encoding="utf-8-sig")

    recommendation, reason = review_recommendation(review_history, result)
    summary_path = REVIEW_DIR / f"晚間策略複盤_{TODAY.isoformat()}.txt"
    summary = [
        f"晚間選股策略複盤：{TODAY.isoformat()}",
        f"上午選股資料日期：{payload.get('recommendation_data_date', '未記錄')}",
        f"當日市場中位數報酬率：{market_return:+.2f}%",
        f"上午候選平均報酬率：{result['當日報酬率'].mean():+.2f}%",
        f"上午候選平均相對市場：{result['相對市場報酬率'].mean():+.2f}%",
        f"策略判斷：{recommendation}",
        f"判斷理由：{reason}",
        "策略治理：本流程不依單日結果自動改權重；正式調整須經離線回測、獨立驗證及前視偏誤檢查。",
    ]
    if t86_error:
        summary.append(f"T86 註記：{t86_error}")
    summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8-sig")
    log.add(f"晚間複盤完成：{summary_path}")

    # 產製晚間策略複盤 PDF 報告
    pdf_review_path = REVIEW_DIR / f"晚間策略複盤_{TODAY.isoformat()}.pdf"
    pdf_root_path = ROOT / f"晚間策略複盤報告_{TODAY.isoformat()}.pdf"
    try:
        create_evening_review_pdf(
            today_str=TODAY.isoformat(),
            data_date_str=payload.get("recommendation_data_date", "未記錄"),
            market_return=market_return,
            df_result=result,
            recommendation=recommendation,
            reason=reason,
            history_df=review_history,
            output_paths=[pdf_review_path, pdf_root_path],
        )
        log.add(f"晚間複盤 PDF 報告產制完成：{pdf_review_path}")
        log.add(f"晚間複盤 PDF 報告副本置於：{pdf_root_path}")
    except Exception as pdf_exc:
        log.add(f"警告：產制晚間複盤 PDF 報告失敗：{pdf_exc}")

    log.add(f"策略判斷：{recommendation}；{reason}")


def create_evening_review_pdf(
    today_str: str,
    data_date_str: str,
    market_return: float,
    df_result: pd.DataFrame,
    recommendation: str,
    reason: str,
    history_df: pd.DataFrame,
    output_paths: list[Path],
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    pyfont = r"C:\Windows\Fonts\msjh.ttc"
    pdfmetrics.registerFont(TTFont("MSJH", pyfont))

    styles = {
        "title": ParagraphStyle("title", fontName="MSJH", fontSize=16, leading=20, textColor=colors.white),
        "subtitle": ParagraphStyle("subtitle", fontName="MSJH", fontSize=8.5, leading=11, textColor=colors.HexColor("#e0f2fe")),
        "h2": ParagraphStyle("h2", fontName="MSJH", fontSize=10.5, leading=14, textColor=colors.HexColor("#075f72"), spaceBefore=6, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="MSJH", fontSize=8, leading=11, textColor=colors.HexColor("#1e293b")),
        "body_bold": ParagraphStyle("body_bold", fontName="MSJH", fontSize=8, leading=11, textColor=colors.HexColor("#0f172a")),
        "small": ParagraphStyle("small", fontName="MSJH", fontSize=7, leading=9, textColor=colors.HexColor("#64748b")),
        "kpi_num": ParagraphStyle("kpi_num", fontName="MSJH", fontSize=12, leading=15, alignment=1),
        "kpi_label": ParagraphStyle("kpi_label", fontName="MSJH", fontSize=7.5, leading=10, textColor=colors.HexColor("#475569"), alignment=1),
        "table_cell": ParagraphStyle("table_cell", fontName="MSJH", fontSize=7.5, leading=10, textColor=colors.HexColor("#1e293b")),
        "table_hdr": ParagraphStyle("table_hdr", fontName="MSJH", fontSize=7.5, leading=10, textColor=colors.white, alignment=1),
    }

    def fmt_val(v, is_pct=True, sign=True):
        if v is None or pd.isna(v):
            return "-"
        v = float(v)
        if is_pct:
            return f"{v:+.2f}%" if sign else f"{v:.2f}%"
        return f"{v:+.1f}" if sign else f"{v:.1f}"

    def color_para(val_str, val_num, styles, align=1):
        if val_num is None or pd.isna(val_num):
            cls = "#475569"
        elif val_num > 0:
            cls = "#c33b32"  # 台股習慣：紅漲
        elif val_num < 0:
            cls = "#16834a"  # 台股習慣：綠跌
        else:
            cls = "#334155"
        style = ParagraphStyle("cp", parent=styles["body"], textColor=colors.HexColor(cls), alignment=align)
        return Paragraph(f"<b>{val_str}</b>", style)

    avg_ret = float(df_result["當日報酬率"].mean()) if not df_result.empty else 0.0
    avg_rel = float(df_result["相對市場報酬率"].mean()) if not df_result.empty else 0.0
    win_count = int((df_result["相對市場報酬率"] > 0).sum()) if not df_result.empty else 0
    total_count = len(df_result)
    win_pct = (win_count / total_count * 100) if total_count > 0 else 0.0
    down_count = int((df_result["當日報酬率"] < 0).sum()) if not df_result.empty else 0

    story = []

    # KPI Banner (4 Blocks)
    kpi_data = [
        [
            Paragraph("當日市場中位數報酬率", styles["kpi_label"]),
            Paragraph("上午選股平均報酬率", styles["kpi_label"]),
            Paragraph("平均相對市場 (超額)", styles["kpi_label"]),
            Paragraph("超越大盤勝率 (相對正報酬)", styles["kpi_label"]),
        ],
        [
            color_para(fmt_val(market_return), market_return, styles, align=1),
            color_para(fmt_val(avg_ret), avg_ret, styles, align=1),
            color_para(fmt_val(avg_rel), avg_rel, styles, align=1),
            Paragraph(f"<b><font color='#075f72'>{win_pct:.0f}%</font></b> ({win_count}/{total_count}檔)", ParagraphStyle("kpib", parent=styles["kpi_num"], alignment=1)),
        ]
    ]
    t_kpi = Table(kpi_data, colWidths=[1.93*inch, 1.93*inch, 1.93*inch, 1.95*inch])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f0fdf4") if avg_rel >= 0 else colors.HexColor("#fff1f2")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 8))

    # Decision & Governance Box
    dec_color = "#0369a1" if "維持" in recommendation else "#b91c1c"
    dec_box_data = [
        [Paragraph(f"<b>策略評估結論：<font color='{dec_color}'>{recommendation}</font></b>", styles["body_bold"])],
        [Paragraph(f"<b>判斷理由：</b>{reason}", styles["body"])],
        [Paragraph("<b>治理規範：</b>本流程遵循嚴格量化治理規範，不依單日結果自動改權重；正式調整須經離線回測、獨立驗證與前視偏誤檢查。", styles["small"])]
    ]
    t_dec = Table(dec_box_data, colWidths=[7.74*inch])
    t_dec.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#075f72")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_dec)
    story.append(Spacer(1, 8))

    # Today's Details Table
    story.append(Paragraph("<b>一、當日選股明細與市場數據比較</b>", styles["h2"]))
    
    headers = ["排名", "代號", "股票名稱", "模型分數", "開盤價", "收盤價", "當日報酬率", "相對市場", "法人買賣超", "複盤發現診斷"]
    tbl_rows = [[Paragraph(f"<b>{h}</b>", styles["table_hdr"]) for h in headers]]

    for _, r in df_result.sort_values("上午排名").iterrows():
        rank_str = str(int(r["上午排名"])) if pd.notna(r["上午排名"]) else "-"
        code_str = str(r["股票代號"])
        name_str = str(r["股票名稱"])
        score_str = f"{float(r['上午分數']):.3f}" if pd.notna(r['上午分數']) else "-"
        open_str = f"{float(r['開盤價']):.2f}" if pd.notna(r['開盤價']) else "-"
        close_str = f"{float(r['收盤價']):.2f}" if pd.notna(r['收盤價']) else "-"
        
        ret_val = float(r["當日報酬率"]) if pd.notna(r["當日報酬率"]) else None
        rel_val = float(r["相對市場報酬率"]) if pd.notna(r["相對市場報酬率"]) else None
        inst_val = float(r["法人買賣超張數"]) if pd.notna(r["法人買賣超張數"]) else None

        ret_p = color_para(fmt_val(ret_val), ret_val, styles, align=1)
        rel_p = color_para(fmt_val(rel_val), rel_val, styles, align=1)
        inst_p = color_para(f"{inst_val:+.0f}" if inst_val is not None else "-", inst_val, styles, align=1)
        
        finding_str = str(r["複盤發現"])

        row = [
            Paragraph(rank_str, ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
            Paragraph(code_str, ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
            Paragraph(f"<b>{name_str}</b>", ParagraphStyle("c", parent=styles["table_cell"], alignment=0)),
            Paragraph(score_str, ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
            Paragraph(open_str, ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
            Paragraph(close_str, ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
            ret_p,
            rel_p,
            inst_p,
            Paragraph(finding_str, ParagraphStyle("c", parent=styles["table_cell"], fontSize=7, leading=9)),
        ]
        tbl_rows.append(row)

    col_w = [0.40*inch, 0.50*inch, 0.85*inch, 0.65*inch, 0.55*inch, 0.55*inch, 0.75*inch, 0.75*inch, 0.85*inch, 1.89*inch]
    t_detail = Table(tbl_rows, colWidths=col_w, repeatRows=1)
    t_detail.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#075f72")),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_detail)
    story.append(Spacer(1, 8))

    # History Daily Summary Table
    story.append(Paragraph("<b>二、近 10 個交易日策略與市場對比歷史軌跡</b>", styles["h2"]))
    if not history_df.empty:
        hist_dates = sorted(history_df["複盤日期"].astype(str).unique())[-10:]
        h_rows = [
            [
                Paragraph("<b>複盤日期</b>", styles["table_hdr"]),
                Paragraph("<b>選股檔數</b>", styles["table_hdr"]),
                Paragraph("<b>平均報酬率</b>", styles["table_hdr"]),
                Paragraph("<b>相對市場超額</b>", styles["table_hdr"]),
                Paragraph("<b>超越大盤勝率</b>", styles["table_hdr"]),
                Paragraph("<b>當日主要觀察診斷</b>", styles["table_hdr"]),
            ]
        ]
        for d in reversed(hist_dates):
            sub = history_df[history_df["複盤日期"].astype(str) == d]
            cnt = len(sub)
            h_ret = float(pd.to_numeric(sub["當日報酬率"], errors="coerce").mean())
            h_rel = float(pd.to_numeric(sub["相對市場報酬率"], errors="coerce").mean())
            h_win = float((pd.to_numeric(sub["相對市場報酬率"], errors="coerce") > 0).mean() * 100)
            
            h_down = int((pd.to_numeric(sub["當日報酬率"], errors="coerce") < 0).sum())
            diag = f"{cnt-h_down}/{cnt} 檔上漲或平盤" if h_down < cnt else f"{h_down}/{cnt} 檔開盤至收盤下跌"

            h_rows.append([
                Paragraph(d, ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
                Paragraph(str(cnt), ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
                color_para(fmt_val(h_ret), h_ret, styles, align=1),
                color_para(fmt_val(h_rel), h_rel, styles, align=1),
                Paragraph(f"{h_win:.0f}%", ParagraphStyle("c", parent=styles["table_cell"], alignment=1)),
                Paragraph(diag, ParagraphStyle("c", parent=styles["table_cell"], fontSize=7)),
            ])
        
        t_hist = Table(h_rows, colWidths=[1.10*inch, 0.70*inch, 1.14*inch, 1.30*inch, 1.20*inch, 2.30*inch], repeatRows=1)
        t_hist.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#334155")),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(t_hist)

    def draw_page(canvas, doc):
        w, h = letter
        canvas.setFillColor(colors.HexColor("#075f72"))
        canvas.rect(0, h - 0.75 * inch, w, 0.75 * inch, fill=1, stroke=0)
        canvas.setFont("MSJH", 16)
        canvas.setFillColor(colors.white)
        canvas.drawString(0.4 * inch, h - 0.38 * inch, "晚間選股策略複盤報告")
        canvas.setFont("MSJH", 8.5)
        canvas.setFillColor(colors.HexColor("#e0f2fe"))
        canvas.drawString(0.4 * inch, h - 0.58 * inch, f"複盤日期：{today_str} ｜ 上午選股資料日期：{data_date_str}")
        
        canvas.setFillColor(colors.HexColor("#075f72"))
        canvas.rect(0, 0, w, 0.22 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("MSJH", 6.7)
        canvas.drawString(0.4 * inch, 0.07 * inch, "紅色為上漲／正報酬，綠色為下跌／負報酬。當日報酬計算方式：(收盤價 - 開盤價) / 開盤價。僅供量化策略檢視與研究參考。")
        canvas.drawRightString(w - 0.4 * inch, 0.07 * inch, f"第 {doc.page} 頁")

    for raw_path in output_paths:
        path = raw_path
        if path.exists():
            try:
                with open(path, "ab"):
                    pass
            except PermissionError:
                root = path.parent / path.stem
                ext = path.suffix
                ts = datetime.now().strftime("%H%M%S")
                path = Path(f"{root}_{ts}{ext}")
        try:
            doc = BaseDocTemplate(
                str(path),
                pagesize=letter,
                leftMargin=0.38 * inch,
                rightMargin=0.38 * inch,
                topMargin=0.9 * inch,
                bottomMargin=0.35 * inch,
            )
            frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
            doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=draw_page)])
            doc.build(list(story))
        except Exception as exc:
            print(f"產生 PDF {path} 時發生例外：{exc}")



def main() -> int:
    parser = argparse.ArgumentParser(description="平日投資報告與晚間複盤")
    parser.add_argument("--mode", choices=("morning", "evening"), required=True)
    parser.add_argument("--allow-weekend", action="store_true")
    args = parser.parse_args()
    log = RunLog(args.mode)
    try:
        if TODAY.weekday() >= 5 and not args.allow_weekend:
            log.add("今日為週末，依規格不執行。")
            log.save("略過")
            return 0
        log.add(f"開始執行：{args.mode}；專案根目錄：{ROOT}")
        if args.mode == "morning":
            run_morning(log)
        else:
            run_evening(log)
        log.save("成功")
        return 0
    except Exception as exc:
        log.add(f"失敗原因：{type(exc).__name__}：{exc}")
        log.add(traceback.format_exc().rstrip())
        log.save("失敗")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
