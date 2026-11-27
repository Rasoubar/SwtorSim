"""Exports docs/modifier_bucketing_master_checklist.md to a publication-quality PDF

Uses Chrome or Microsoft Edge headless mode with MathJax / GitHub-style CSS.
"""

import os
import subprocess
import sys
from pathlib import Path


def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def markdown_to_html(md_text):
    # Minimal custom renderer for checklist markdown
    lines = md_text.replace("\r\n", "\n").split("\n")
    html = []
    in_table = False
    in_math = False
    math_lines = []

    for line in lines:
        stripped = line.strip()

        # Math blocks
        if stripped == "$$":
            if in_math:
                math_content = " ".join(math_lines)
                html.append(f'<div class="math-display">\\[{math_content}\\]</div>')
                in_math = False
                math_lines = []
            else:
                in_math = True
                math_lines = []
            continue

        if in_math:
            math_lines.append(line)
            continue

        # Tables
        if line.startswith("|") and line.endswith("|"):
            if not in_table:
                in_table = True
                html.append("<table>")

            # Check separator line
            if re.match(r"^\|(\s*:?-+:?\s*\|)+$", stripped):
                continue

            cells = [c.strip() for c in stripped[1:-1].split("|")]
            # Check if header (first row in table)
            if html[-1] == "<table>":
                row_html = "".join(f"<th>{inline_formatting(c)}</th>" for c in cells)
                html.append(f"<thead><tr>{row_html}</tr></thead><tbody>")
            else:
                row_html = "".join(f"<td>{inline_formatting(c)}</td>" for c in cells)
                html.append(f"<tr>{row_html}</tr>")
            continue
        else:
            if in_table:
                html.append("</tbody></table>")
                in_table = False

        if not stripped:
            continue

        # Headings
        if stripped.startswith("#### "):
            html.append(f"<h4>{inline_formatting(stripped[5:])}</h4>")
        elif stripped.startswith("### "):
            html.append(f"<h3>{inline_formatting(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            html.append(f"<h2>{inline_formatting(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            html.append(f"<h1>{inline_formatting(stripped[2:])}</h1>")
        elif stripped.startswith("---"):
            html.append("<hr>")
        elif stripped.startswith("> [!NOTE]"):
            html.append('<div class="alert alert-note"><strong>Note:</strong>')
        elif stripped.startswith("> "):
            if html and '<div class="alert' in html[-1]:
                html[-1] += f" {inline_formatting(stripped[2:])}</div>"
            else:
                html.append(f"<blockquote>{inline_formatting(stripped[2:])}</blockquote>")
        elif stripped.startswith("* **") or stripped.startswith("  * `"):
            # List items
            indent = len(line) - len(line.lstrip())
            css_class = "list-sub" if indent > 0 else "list-main"
            item_text = stripped.lstrip("* ").strip()
            html.append(f'<div class="{css_class}">&bull; {inline_formatting(item_text)}</div>')
        else:
            html.append(f"<p>{inline_formatting(stripped)}</p>")

    if in_table:
        html.append("</tbody></table>")

    return "\n".join(html)


import re

def inline_formatting(text):
    # Bold `**text**`
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Inline code `` `code` ``
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Links `[text](url)`
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    # Inline math `$math$`
    text = re.sub(r"\$([^\$]+)\$", r"\\(\1\\)", text)
    return text


TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>SWTOR Combat Modifier Master Bucketing Checklist</title>
<script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>
  @page {
    size: A4 portrait;
    margin: 1.5cm;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #1f2328;
    background: #ffffff;
    line-height: 1.5;
    font-size: 13px;
    padding: 0;
    margin: 0;
  }
  h1 {
    font-size: 22px;
    border-bottom: 2px solid #d0d7de;
    padding-bottom: 8px;
    margin-top: 0;
    color: #0969da;
  }
  h2 {
    font-size: 17px;
    border-bottom: 1px solid #d0d7de;
    padding-bottom: 5px;
    margin-top: 24px;
    color: #1f2328;
  }
  h3 {
    font-size: 14px;
    margin-top: 18px;
    margin-bottom: 6px;
    color: #1f2328;
  }
  h4 {
    font-size: 13px;
    margin-top: 12px;
    margin-bottom: 4px;
    color: #57606a;
  }
  p {
    margin: 6px 0;
  }
  hr {
    border: 0;
    height: 1px;
    background: #d0d7de;
    margin: 18px 0;
  }
  code {
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    font-size: 11.5px;
    background: #f6f8fa;
    padding: 2px 5px;
    border-radius: 4px;
    border: 1px solid #e1e4e8;
    color: #0550ae;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 11.5px;
    page-break-inside: auto;
  }
  tr {
    page-break-inside: avoid;
    page-break-after: auto;
  }
  th, td {
    border: 1px solid #d0d7de;
    padding: 6px 8px;
    text-align: left;
    vertical-align: top;
  }
  th {
    background-color: #f6f8fa;
    font-weight: 600;
  }
  tr:nth-child(even) td {
    background-color: #fbfcfd;
  }
  .alert-note {
    background-color: #ddf4ff;
    border-left: 4px solid #0969da;
    padding: 8px 12px;
    margin: 10px 0;
    border-radius: 4px;
    font-size: 12px;
  }
  .math-display {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    padding: 12px;
    border-radius: 6px;
    margin: 12px 0;
    overflow-x: auto;
    text-align: center;
  }
  .list-main {
    margin-left: 8px;
    margin-top: 3px;
    margin-bottom: 2px;
  }
  .list-sub {
    margin-left: 28px;
    margin-top: 2px;
    margin-bottom: 2px;
    color: #424a53;
  }
  a {
    color: #0969da;
    text-decoration: none;
  }
</style>
</head>
<body>
CONTENT_PLACEHOLDER
</body>
</html>
"""


def main():
    browser = find_browser()
    if not browser:
        print("[FAIL] No Chromium-based browser (Chrome or Edge) found for PDF generation.")
        sys.exit(1)

    chk_path = Path("docs/modifier_bucketing_master_checklist.md")
    if not chk_path.exists():
        print(f"[FAIL] Missing {chk_path}")
        sys.exit(1)

    md_text = chk_path.read_text(encoding="utf-8")
    body_html = markdown_to_html(md_text)
    full_html = TEMPLATE.replace("CONTENT_PLACEHOLDER", body_html)

    tmp_html = Path("docs/modifier_bucketing_master_checklist.html")
    pdf_out = Path("docs/modifier_bucketing_master_checklist.pdf")

    tmp_html.write_text(full_html, encoding="utf-8")
    print(f"[*] Generated standalone HTML at: {tmp_html}")

    print(f"[*] Printing PDF via {browser}...")
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=2000",
        f"--print-to-pdf={pdf_out.resolve()}",
        str(tmp_html.resolve()),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and pdf_out.exists():
        size_kb = pdf_out.stat().st_size / 1024.0
        print(f"[OK] Successfully generated PDF at: {pdf_out} ({size_kb:.1f} KB)")
    else:
        print(f"[FAIL] PDF printing failed: {res.stderr}")


if __name__ == "__main__":
    main()
