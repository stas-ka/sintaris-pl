#!/usr/bin/env python3
"""parse_doc.py — Document parser for KB ingest pipeline.

Called by N8N Execute Command node inside the KB - Ingest workflow.
Parses a document file using Docling (if installed) with fallback to
pdfminer.six for PDFs and plain text for .txt/.md files.

Usage:
    python3 /opt/taris-mcp-kb/parse_doc.py <filepath> <title>

Output:
    JSON to stdout:
      {"ok": true, "pages": [{"section": "...", "text": "..."}], "title": "..."}
      {"ok": false, "error": "..."}

Install to VPS:
    sudo cp deploy/system-configs/vps/mcp-kb/parse_doc.py /opt/taris-mcp-kb/parse_doc.py
    pip3 install docling          # recommended; fallback works without it
    pip3 install pdfminer.six     # fallback for PDF
"""
import json
import os
import sys


def parse_with_docling(filepath: str, title: str) -> dict:
    from docling.document_converter import DocumentConverter
    conv = DocumentConverter()
    result = conv.convert(filepath)
    doc = result.document

    pages = []
    current_section = ""

    for item, _level in doc.iterate_items():
        cls = type(item).__name__
        # Headings / section titles become the running section label
        if any(t in cls for t in ("Title", "Heading", "SectionHeader", "Caption")):
            current_section = getattr(item, "text", str(item))[:200]
        elif hasattr(item, "text") and item.text and item.text.strip():
            pages.append({"section": current_section, "text": item.text.strip()})

    # Fallback: export to markdown if nothing was extracted
    if not pages:
        md = doc.export_to_markdown()
        if md.strip():
            pages = [{"section": "", "text": md}]

    return {"ok": True, "pages": pages, "title": title}


def parse_with_fallback(filepath: str, title: str) -> dict:
    ext = os.path.splitext(filepath)[1].lower()
    text = ""

    if ext == ".pdf":
        from pdfminer.high_level import extract_text
        text = extract_text(filepath) or ""
    elif ext in (".txt", ".md", ".rst", ".csv"):
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    elif ext in (".docx",):
        try:
            import docx
            d = docx.Document(filepath)
            text = "\n".join(p.text for p in d.paragraphs)
        except ImportError:
            text = f"[.docx parsing requires python-docx. Install: pip3 install python-docx]"
    else:
        text = f"[Unsupported format: {ext}. Install docling for broader format support.]"

    pages = [{"section": "", "text": text}] if text.strip() else []
    return {"ok": True, "pages": pages, "title": title, "fallback": True}


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: parse_doc.py <filepath> <title>"}))
        sys.exit(1)

    filepath = sys.argv[1]
    title = sys.argv[2]

    if not os.path.exists(filepath):
        print(json.dumps({"ok": False, "error": f"File not found: {filepath}"}))
        sys.exit(1)

    try:
        result = parse_with_docling(filepath, title)
    except ImportError:
        try:
            result = parse_with_fallback(filepath, title)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"Fallback parse failed: {exc}"}))
            sys.exit(1)
    except Exception as exc:
        # Docling installed but parsing failed — try fallback
        try:
            result = parse_with_fallback(filepath, title)
            result["docling_error"] = str(exc)
        except Exception as exc2:
            print(json.dumps({"ok": False, "error": f"All parsers failed: {exc} / {exc2}"}))
            sys.exit(1)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
