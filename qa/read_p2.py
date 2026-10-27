# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from pypdf import PdfReader
root = Path(r'C:\Users\User\Desktop\股市')
pdf1 = root / '全球投資市場研究報告_2026-10-27.pdf'
reader = PdfReader(str(pdf1))
p2 = reader.pages[1].extract_text()
print('=== PAGE 2 TEXT ===')
print(p2)
