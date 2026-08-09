"""
PDF Export Service — generates a formatted government GR PDF via WeasyPrint.
Fully offline, no external API required.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Ensure macOS Homebrew dynamic library path is registered for cffi/pango/gobject
if sys.platform == "darwin":
    for lib_dir in ["/opt/homebrew/lib", "/usr/local/lib"]:
        if os.path.exists(lib_dir):
            curr = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            if lib_dir not in curr:
                os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = f"{lib_dir}:{curr}".strip(":")


# ── HTML Template ─────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="mr">
<head>
  <meta charset="UTF-8">
  <style>
    @page {{
      margin: {margins_pt}pt;
      size: A4;
    }}
    body {{
      font-family: "{font_family}", "Noto Sans", "Lohit Devanagari", sans-serif;
      font-size: 12pt;
      line-height: 1.8;
      color: #111;
    }}
    .letterhead {{
      text-align: center;
      border-bottom: 3px double #1a3a6e;
      padding-bottom: 12pt;
      margin-bottom: 18pt;
    }}
    .letterhead-logo {{
      height: 70pt;
      margin-bottom: 6pt;
    }}
    .letterhead-dept {{
      font-size: 20pt;
      font-weight: bold;
      color: #1a3a6e;
      letter-spacing: 1pt;
    }}
    .letterhead-subdept {{
      font-size: 14pt;
      color: #333;
      margin-top: 2pt;
    }}
    .gr-meta {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20pt;
      font-size: 11pt;
    }}
    .gr-meta td {{
      padding: 4pt 8pt;
      vertical-align: top;
    }}
    .gr-meta .label {{
      font-weight: bold;
      width: 30%;
      color: #444;
    }}
    .section-title {{
      font-size: 13pt;
      font-weight: bold;
      color: #1a3a6e;
      border-bottom: 1px solid #aac;
      margin: 14pt 0 8pt;
      padding-bottom: 3pt;
    }}
    .gr-body {{
      white-space: pre-wrap;
      word-break: break-word;
      text-align: justify;
      font-size: 12pt;
      line-height: 2;
    }}
    .footer {{
      margin-top: 36pt;
      border-top: 1px solid #aac;
      padding-top: 10pt;
      font-size: 10pt;
      color: #555;
      display: flex;
      justify-content: space-between;
    }}
    .approval-badges {{
      margin: 16pt 0;
      padding: 10pt 14pt;
      background: #eef6ff;
      border-left: 4px solid #1a3a6e;
      border-radius: 4pt;
    }}
    .approval-badge {{
      display: inline-block;
      margin: 3pt 6pt 3pt 0;
      padding: 3pt 10pt;
      background: #1a3a6e;
      color: white;
      border-radius: 12pt;
      font-size: 10pt;
    }}
    .page-number::after {{
      content: counter(page) " / " counter(pages);
    }}
  </style>
</head>
<body>

  <!-- Letterhead -->
  <div class="letterhead">
    {logo_img}
    <div class="letterhead-dept">{department}</div>
    <div class="letterhead-subdept">{header_line}</div>
  </div>

  <!-- GR Metadata -->
  <table class="gr-meta">
    <tr>
      <td class="label">GR क्रमांक:</td>
      <td>{gr_number}</td>
      <td class="label">दिनांक:</td>
      <td>{gr_date}</td>
    </tr>
    <tr>
      <td class="label">विभाग:</td>
      <td colspan="3">{department}</td>
    </tr>
    <tr>
      <td class="label">विषय:</td>
      <td colspan="3">{subject}</td>
    </tr>
  </table>

  <!-- Approval Badges -->
  {approval_section}

  <!-- Body -->
  <div class="section-title">शासन निर्णय</div>
  <div class="gr-body">{body_text}</div>

  <!-- Footer -->
  <div class="footer">
    <span>{footer_text}</span>
    <span class="page-number"></span>
  </div>

</body>
</html>
"""

# ── Public API ─────────────────────────────────────────────────────────────────


def generate_gr_pdf(
    doc: dict,
    template: dict,
    approval_notes: list[dict] | None = None,
) -> bytes:
    """
    Render a GR document as a styled PDF using WeasyPrint.

    Args:
        doc: draft document dict (id, filename, full_text, subject_mr, etc.)
        template: PDF template row from gr_pdf_template table
        approval_notes: list of approval_note comments (user_name, user_role)

    Returns:
        PDF bytes
    """
    from weasyprint import HTML

    margins_pt = int(template.get("margins_pt") or 72)
    font_family = template.get("font_family") or "Noto Sans"
    department = template.get("department") or "महाराष्ट्र शासन"
    header_line = template.get("header_line") or "उच्च व तंत्र शिक्षण विभाग"
    footer_text = template.get("footer_text") or "महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने"

    # Logo
    logo_base64 = template.get("logo_base64") or ""
    if logo_base64:
        logo_img = f'<img class="letterhead-logo" src="data:image/png;base64,{logo_base64}" alt="Logo" />'
    else:
        # Embed Maharashtra seal if no custom logo provided
        seal_path = _find_seal_path()
        if seal_path:
            with open(seal_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
            logo_img = f'<img class="letterhead-logo" src="data:image/svg+xml;base64,{logo_b64}" alt="Maharashtra Seal" />'
        else:
            logo_img = ""

    # Approval badges section
    if approval_notes:
        badges = "".join(
            f'<span class="approval-badge">✅ {a["user_name"]} ({a["user_role"]})</span>'
            for a in approval_notes
        )
        approval_section = f'<div class="approval-badges"><strong>अनुमोदन / Approved By:</strong><br>{badges}</div>'
    else:
        approval_section = ""

    # GR metadata
    gr_number = doc.get("gr_number_canonical") or doc.get("filename") or "—"
    gr_date = doc.get("gr_date") or doc.get("date") or "—"
    subject = doc.get("subject_mr") or doc.get("subject") or "—"
    body_text = doc.get("full_text") or doc.get("ocr_text") or ""

    html_content = _HTML_TEMPLATE.format(
        margins_pt=margins_pt,
        font_family=font_family,
        department=department,
        header_line=header_line,
        footer_text=footer_text,
        logo_img=logo_img,
        gr_number=gr_number,
        gr_date=gr_date,
        subject=subject,
        approval_section=approval_section,
        body_text=body_text,
    )

    logger.info("Generating GR PDF for doc_id=%s (%d chars body)", doc.get("id"), len(body_text))

    pdf_bytes_io = io.BytesIO()
    HTML(string=html_content).write_pdf(pdf_bytes_io)
    pdf_bytes_io.seek(0)
    return pdf_bytes_io.read()


def _find_seal_path() -> str | None:
    """Find the Maharashtra government seal SVG in the frontend public assets."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "Seal_of_Maharashtra.svg"),
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "assets", "Seal_of_Maharashtra.svg"),
    ]
    for p in candidates:
        normalized = os.path.normpath(p)
        if os.path.exists(normalized):
            return normalized
    return None
