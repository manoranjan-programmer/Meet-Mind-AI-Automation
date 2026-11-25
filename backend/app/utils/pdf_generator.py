import io
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

def generate_meeting_summary_pdf(meeting_doc: Dict[str, Any]) -> bytes:
    """Generates a clean PDF document for meeting summary, decisions, and action items."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A')
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#2563EB'),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155')
    )

    meta_style = ParagraphStyle(
        'MetaText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#64748B')
    )

    story = []

    # Title & Branding
    story.append(Paragraph("MeetMind AI – Meeting Intelligence Report", meta_style))
    story.append(Spacer(1, 4))
    title = meeting_doc.get("meeting_title") or meeting_doc.get("title") or "Meeting Summary"
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 6))

    # Meta Table (Date, Duration, Lead)
    created_date = meeting_doc.get("created_at")
    date_str = created_date.strftime("%B %d, %Y %H:%M UTC") if hasattr(created_date, "strftime") else str(created_date or "")
    duration_str = str(meeting_doc.get("duration") or "00:00")
    lead_str = str(meeting_doc.get("team_lead_email") or "Admin")

    meta_data = [
        [
            Paragraph(f"<b>Meeting ID:</b> {meeting_doc.get('meeting_id')}", meta_style),
            Paragraph(f"<b>Date:</b> {date_str}", meta_style),
            Paragraph(f"<b>Duration:</b> {duration_str}", meta_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[160, 220, 150])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceAfter=14))

    # Executive Summary
    story.append(Paragraph("Executive Summary", h2_style))
    summary_text = meeting_doc.get("meeting_summary") or meeting_doc.get("summary") or "No summary recorded."
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 12))

    # Key Decisions
    decisions = meeting_doc.get("key_decisions", [])
    if decisions:
        story.append(Paragraph("Key Decisions Confirmed", h2_style))
        for d in decisions:
            story.append(Paragraph(f"• {d}", body_style))
        story.append(Spacer(1, 12))

    # Action Items / Deliverables
    action_items = meeting_doc.get("action_items", [])
    if action_items:
        story.append(Paragraph("Extracted Deliverables & Action Items", h2_style))
        for item in action_items:
            item_text = item if isinstance(item, str) else item.get("title", str(item))
            story.append(Paragraph(f"✓ {item_text}", body_style))
        story.append(Spacer(1, 12))

    # Participants
    participants = meeting_doc.get("participants", [])
    if participants:
        story.append(Paragraph("Participants", h2_style))
        p_str = ", ".join(participants) if isinstance(participants, list) else str(participants)
        story.append(Paragraph(p_str, body_style))
        story.append(Spacer(1, 14))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceBefore=10, spaceAfter=8))
    story.append(Paragraph("Generated autonomously by MeetMind AI Multi-Agent Intelligence System.", meta_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
