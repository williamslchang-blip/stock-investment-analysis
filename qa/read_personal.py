# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from pypdf import PdfReader
root = Path(r'C:\Users\User\Desktop\股市')
pdf2 = root / '個人投資部位分析報告_2026-10-27.pdf'
reader = PdfReader(str(pdf2))
print('=== PERSONAL REPORT P1 ===')
print(reader.pages[0].extract_text()[:400])
print('=== PERSONAL REPORT P2 ===')
print(reader.pages[1].extract_text()[:400])
