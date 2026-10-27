import sys, os, re

path = r'C:\Users\User\Desktop\股市\programs\generate_daily_investment_reports.py'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Helper function to build news sub-industry and stock recommendations
helper_func = '''def build_news_industry_and_stock_recommendations(news_items):
    sub_industries = []
    featured_stocks = []
    
    keywords_map = [
        ('半導體', '半導體先進封裝', ['2330 台積電', '2303 聯電', '3711 日月光']),
        ('CoWoS', 'CoWoS 先進封裝', ['2330 台積電', '3583 辛耘', '6187 萬潤']),
        ('矽光子', '矽光子 CPO 光通訊', ['3450 聯鈞', '4979 華星光', '3363 上詮']),
        ('AI', 'AI 伺服器與水冷散熱', ['2382 廣達', '3231 緯創', '6669 緯穎', '3017 奇鋐']),
        ('散熱', '水冷散熱與機櫃系統', ['3017 奇鋐', '3324 雙鴻']),
        ('重電', '重電綠能與強韌電網', ['1519 華城', '1503 士電', '1513 中興電']),
        ('記憶體', '高頻寬記憶體 HBM', ['2408 南亞科', '3260 威剛']),
        ('機器人', 'AI 機器人與自動化', ['2359 所羅門', '4583 台灣精銳']),
    ]
    
    if news_items:
        for item in news_items:
            full = (item.get('title', '') + ' ' + item.get('summary', '')).upper()
            for k, sub_ind, stocks in keywords_map:
                if k.upper() in full:
                    if sub_ind not in sub_industries: sub_industries.append(sub_ind)
                    for st in stocks:
                        if st not in featured_stocks: featured_stocks.append(st)
                    
    if not sub_industries:
        sub_industries = ['半導體與 CoWoS 先進封裝', 'AI 伺服器與水冷散熱', '矽光子 CPO 光通訊']
        featured_stocks = ['2330 台積電', '2382 廣達', '3231 緯創', '3017 奇鋐']
        
    sub_ind_str = "、".join(sub_industries[:3])
    stocks_str = "、".join(featured_stocks[:5])
    
    text = (
        f"<b>各大報熱門子產業與新聞推介個股 (源自各大報報導，非本模型計算)</b><br/>"
        f"<b>• 熱門子產業選擇建議：</b>{sub_ind_str}<br/>"
        f"<b>• 各大報新聞焦點推介個股：</b>{stocks_str}<br/>"
        f"<font size='6.5' color='#6b7280'>註：本欄位子產業與推介個股完全源自國內各大財經日報新聞報導與媒體分析，非本 PDF 學術 10 指標模型計算建議。</font>"
    )
    return text
'''

if 'def build_news_industry_and_stock_recommendations' not in content:
    content = content.replace('def build_global_report(', helper_func + '\n\ndef build_global_report(')

old_line = 'story.append(Paragraph("今日觀察重點：1. 三大法人與外資期貨淨部位是否同步偏空；2. 台幣是否續貶；3. AI/半導體財報利多能否帶動量價轉強；4. 油價下跌是否降低通膨壓力；5. 衛星股是否跌破 MA20 或出現放量下跌。", styles["body"]))'

new_line = '''    news_rec_text = build_news_industry_and_stock_recommendations(news_items)
    news_rec_panel = Table(
        [[Paragraph(news_rec_text, info_style)]],
        colWidths=[6.35 * inch],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#5a86b5")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f9fd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )
    story.append(news_rec_panel)'''

content = content.replace(old_line, new_line)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('SUCCESSFULLY UPDATED PAGE 2 BOTTOM NEWS SUB-INDUSTRY & FEATURED STOCKS PANEL!')
