#!/usr/bin/env python
"""
Debug script to inspect paragraph styles in a DOCX file.
Usage: python debug_docx_styles.py <path-to-docx>
"""
import sys
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

if len(sys.argv) < 2:
    print("Usage: python debug_docx_styles.py <path-to-docx>")
    sys.exit(1)

docx_path = Path(sys.argv[1])
if not docx_path.exists():
    print(f"File not found: {docx_path}")
    sys.exit(1)

doc = Document(docx_path)
print(f"\n📄 Analyzing: {docx_path.name}\n")

para_index = 0
for para in doc.paragraphs:
    para_index += 1
    text = para.text.strip()[:50]  # First 50 chars
    style_name = para.style.name
    
    # Check if it has numbering properties
    ppr = para._p.pPr
    has_numpr = ppr is not None and ppr.numPr is not None
    numid = None
    if has_numpr and ppr.numPr.numId is not None:
        numid = ppr.numPr.numId.val
    
    marker = "📋 LIST" if has_numpr else "  TEXT"
    print(f"{marker} | Para #{para_index:2d} | Style: '{style_name}'")
    if text:
        print(f"       | Text: {text}...")
    if numid:
        print(f"       | numId: {numid}")
    print()

print(f"Total paragraphs: {para_index}")
