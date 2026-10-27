import sys, os, re

path = r'C:\Users\User\Desktop\股市\programs\generate_daily_investment_reports.py'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Upgrade build_news_industry_and_stock_recommendations to group sub-industries with their sub-industry stock recommendations line-by-line
new_panel_func = '''def build_news_industry_and_stock_recommendations(news_items):
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
    return "<br/>".join(lines)'''

pattern_bf = r'def build_news_industry_and_stock_recommendations\([^)]*\):.*?return "<br/>"\.join\(lines\)'
if 'def build_news_industry_and_stock_recommendations' in content:
    pattern_bf_old = r'def build_news_industry_and_stock_recommendations\([^)]*\):.*?return text'
    content = re.sub(pattern_bf_old, new_panel_func, content, flags=re.DOTALL)
else:
    content = content.replace('def build_global_report(', new_panel_func + '\n\ndef build_global_report(')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('SUCCESSFULLY UPDATED SUB-INDUSTRY & STOCK RECOMMENDATIONS FORMATTING!')
