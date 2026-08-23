"""Render stored report content_json as a downloadable PDF (no LLM calls)."""

from __future__ import annotations

from typing import Any

from fpdf import FPDF

from core.models import Report

# Helvetica (built-in) is Latin-1 only — use ASCII status labels, not emoji.
_STATUS_DISPLAY: dict[str, tuple[str, tuple[int, int, int]]] = {
    "supported": ("[OK] Supported", (0, 120, 60)),
    "unsupported": ("[WARN] Unsupported", (180, 90, 0)),
    "uncertain": ("[?] Inconclusive", (90, 90, 90)),
}

_EMOJI_REPLACEMENTS = {
    "\u2705": "[OK]",
    "\u26a0\ufe0f": "[WARN]",
    "\u26a0": "[WARN]",
    "\u2753": "[?]",
    "\u2014": "-",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
}


def _latin1_safe(text: str) -> str:
    """Normalize text for built-in PDF fonts (Latin-1)."""
    if not text:
        return ""
    out = str(text)
    for src, dst in _EMOJI_REPLACEMENTS.items():
        out = out.replace(src, dst)
    return out.encode("latin-1", errors="replace").decode("latin-1")


def _status_label(status: str | None) -> tuple[str, tuple[int, int, int]]:
    key = (status or "uncertain").lower()
    if key not in _STATUS_DISPLAY:
        key = "uncertain"
    return _STATUS_DISPLAY[key]


class _ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def _ensure_space(pdf: _ReportPDF, needed_mm: float) -> None:
    bottom = pdf.h - pdf.b_margin
    if pdf.get_y() + needed_mm > bottom:
        pdf.add_page()


def _section_heading(pdf: _ReportPDF, title: str) -> None:
    _ensure_space(pdf, 14)
    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 7, _latin1_safe(title))
    pdf.ln(1)


def _body_text(pdf: _ReportPDF, text: str, *, bullet: bool = False) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    prefix = "- " if bullet else ""
    pdf.multi_cell(0, 5, _latin1_safe(prefix + text))


def _draw_claims_table(pdf: _ReportPDF, claims: list[dict[str, Any]]) -> None:
    if not claims:
        return

    margin = pdf.l_margin
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    col_status = 36.0
    col_conf = 22.0
    col_claim = usable - col_status - col_conf
    line_h = 5.0

    _ensure_space(pdf, 16)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(240, 244, 248)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(col_status, 7, "Status", border=1, fill=True)
    pdf.cell(col_claim, 7, "Claim", border=1, fill=True)
    pdf.cell(col_conf, 7, "Conf.", border=1, fill=True, ln=True)

    pdf.set_font("Helvetica", "", 9)
    for claim in claims:
        status = claim.get("verification_status") or "uncertain"
        label, color = _status_label(status)
        statement = _latin1_safe(str(claim.get("statement") or ""))
        conf = claim.get("confidence_score")
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"

        x0 = margin
        y0 = pdf.get_y()
        pdf.set_xy(x0 + col_status, y0)
        split = pdf.multi_cell(col_claim, line_h, statement, border=0, split_only=True)
        if isinstance(split, list):
            claim_h = max(line_h, len(split) * line_h)
        else:
            claim_h = max(line_h, float(split))
        row_h = max(claim_h + 2, line_h + 2)

        bottom = pdf.h - pdf.b_margin
        if y0 + row_h > bottom:
            pdf.add_page()
            y0 = pdf.get_y()

        pdf.set_xy(x0, y0)
        pdf.set_draw_color(200, 200, 200)
        pdf.rect(x0, y0, col_status, row_h)
        pdf.rect(x0 + col_status, y0, col_claim, row_h)
        pdf.rect(x0 + col_status + col_claim, y0, col_conf, row_h)

        pdf.set_xy(x0 + 1, y0 + 1)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*color)
        pdf.multi_cell(col_status - 2, line_h, label, border=0)

        pdf.set_xy(x0 + col_status + 1, y0 + 1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(col_claim - 2, line_h, statement, border=0)

        pdf.set_xy(x0 + col_status + col_claim + 1, y0 + 1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(col_conf - 2, line_h, conf_s, border=0)

        pdf.set_xy(margin, y0 + row_h)

    pdf.set_x(pdf.l_margin)


def _render_pdf(content: dict[str, Any]) -> bytes:
    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(20, 40, 80)
    pdf.cell(0, 10, "Research Report", ln=True)

    question = _latin1_safe(str(content.get("research_question") or ""))
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 6, f"Question: {question}")
    pdf.ln(3)

    _section_heading(pdf, "Executive Summary")
    _body_text(pdf, str(content.get("executive_summary") or ""))

    findings = content.get("key_findings") or []
    if findings:
        _section_heading(pdf, "Key Findings")
        for item in findings:
            _body_text(pdf, str(item), bullet=True)

    claims = content.get("claims_with_verification") or []
    if claims:
        _section_heading(pdf, "Claims & Verification")
        _draw_claims_table(pdf, claims)

    contradictions = content.get("contradictions") or []
    if contradictions:
        _section_heading(pdf, "Contradictions")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(140, 70, 0)
        for item in contradictions:
            if isinstance(item, dict):
                text = str(item.get("description") or item)
            else:
                text = str(item)
            _body_text(pdf, text, bullet=True)

    gaps = content.get("gaps") or []
    if gaps:
        _section_heading(pdf, "Gaps & Limitations (Analysis)")
        for item in gaps:
            _body_text(pdf, str(item), bullet=True)

    limitations = content.get("limitations") or []
    if limitations:
        _section_heading(pdf, "Limitations")
        for item in limitations:
            _body_text(pdf, str(item), bullet=True)

    conclusion = str(content.get("conclusion") or "").strip()
    if conclusion:
        _section_heading(pdf, "Conclusion")
        _body_text(pdf, conclusion)

    sources = content.get("sources") or []
    if sources:
        _section_heading(pdf, "Sources")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        for src in sources:
            label = _latin1_safe(str(src.get("source_type") or "source"))
            url = _latin1_safe(str(src.get("source_url") or "(no url)"))
            _ensure_space(pdf, 8)
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 9)
            pdf.multi_cell(0, 4, f"[{label}]")
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 80, 160)
            pdf.multi_cell(0, 4, url)
            pdf.set_text_color(40, 40, 40)
            pdf.ln(1)

    # fpdf2 returns str when dest=S — we want raw bytes for Streamlit.
    return pdf.output()


def generate_pdf(report: Report | dict[str, Any]) -> bytes:
    """Build a PDF from a Report row or its content_json dict. Pure formatting — no LLM."""
    if isinstance(report, Report):
        content = report.content_json if isinstance(report.content_json, dict) else {}
    else:
        content = report
    if not content:
        raise ValueError("Report has no content_json to export.")
    return _render_pdf(content)
