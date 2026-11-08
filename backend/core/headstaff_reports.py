"""Head Staff-only server-generated operational PDF reports."""
from datetime import date, datetime
from html import escape
from io import BytesIO
import re

from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    AuditLog,
    Barangay,
    BookletReturn,
    DeathRecord,
    GroceryClaim,
    PensionRecord,
    ResidenceTransferRecord,
    SeniorCitizen,
)


class HeadStaffOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (request.user.is_superuser or request.user.role == "head_staff"))


REPORTS = {
    "ncsc_annex_a": ("NCSC Annex A - Milestone-Age Records", "NCSC milestone-age list"),
    "pension_payroll": ("Monthly Pension Claim Report", "Pension payroll"),
    "masterlist": ("Senior Citizen Masterlist", "Senior masterlist"),
    "quarterly_analytics": ("Quarterly OSCA Activity Summary", "Quarterly analytics"),
}
MILESTONE_AGES = (80, 85, 90, 95, 100)


def _period_start(value):
    """Parse YYYY-MM or a month label. Use current month when omitted."""
    if not value:
        today = timezone.localdate()
        return date(today.year, today.month, 1)
    match = re.fullmatch(r"(\d{4})-(\d{2})", value.strip())
    if match:
        year, month = map(int, match.groups())
        if 1 <= month <= 12:
            return date(year, month, 1)
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", value.strip())
    if match:
        try:
            parsed = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%B %Y")
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            pass
    return None


def _month_end(start):
    return date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)


def _query_filters(request):
    month = _period_start(request.query_params.get("month", ""))
    if month is None:
        return None, None, Response({"month": ["Use a month in YYYY-MM format."]}, status=400)
    barangay_value = request.query_params.get("barangay", "").strip()
    barangay = None
    if barangay_value and barangay_value.casefold() not in {"all", "all barangays"}:
        barangay = Barangay.objects.filter(Q(code__iexact=barangay_value) | Q(name__iexact=barangay_value), is_active=True).first()
        if not barangay:
            return None, None, Response({"barangay": ["Choose an active barangay."]}, status=400)
    return month, barangay, None


def _senior_rows(report_key, barangay):
    seniors = SeniorCitizen.objects.select_related("barangay").all()
    if barangay:
        seniors = seniors.filter(barangay=barangay)
    if report_key == "ncsc_annex_a":
        seniors = seniors.filter(is_active=True, milestone_age__in=MILESTONE_AGES)
    rows = []
    for senior in seniors.order_by("barangay__name", "last_name", "first_name"):
        name = " ".join(part for part in [senior.last_name + ",", senior.first_name, senior.middle_name, senior.suffix] if part).strip()
        rows.append([
            senior.osca_id,
            name,
            senior.barangay.name if senior.barangay else "Unassigned",
            senior.age,
            senior.date_of_birth.strftime("%b %d, %Y") if senior.date_of_birth else "",
            senior.get_sex_display(),
            senior.registration_status.title(),
            "Active" if senior.is_active else "Inactive",
        ])
    return rows


def _pension_rows(month, barangay):
    records = PensionRecord.objects.select_related("senior_citizen", "senior_citizen__barangay").all()
    if barangay:
        records = records.filter(senior_citizen__barangay=barangay)
    rows = []
    for record in records.order_by("senior_citizen__barangay__name", "senior_citizen__last_name", "senior_citizen__first_name"):
        parsed = _period_start(record.period)
        if parsed != month:
            continue
        senior = record.senior_citizen
        rows.append([
            record.period,
            senior.osca_id,
            f"{senior.last_name}, {senior.first_name} {senior.middle_name}".strip(),
            senior.barangay.name if senior.barangay else "Unassigned",
            f"PHP {record.amount:,.2f}",
            "Claimed" if record.claimed else "Unclaimed",
            record.date_claimed.strftime("%b %d, %Y") if record.date_claimed else "",
            ("Self" if record.claimed_by == "self" else record.representative or "Authorized representative") if record.claimed else "",
        ])
    return rows


def _quarterly_rows(month, barangay):
    quarter = (month.month - 1) // 3
    start_month = quarter * 3 + 1
    start = date(month.year, start_month, 1)
    end_month = start_month + 3
    end_year = month.year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    end = date(end_year, end_month, 1)
    barangays = Barangay.objects.filter(is_active=True).order_by("name")
    if barangay:
        barangays = barangays.filter(pk=barangay.pk)
    rows = []
    for item in barangays:
        seniors = SeniorCitizen.objects.filter(barangay=item)
        pension = PensionRecord.objects.filter(senior_citizen__barangay=item, claimed=True)
        pension_count = sum(
            1 for period in pension.values_list("period", flat=True)
            if (parsed := _period_start(period)) and start <= parsed < end
        )
        death_count = DeathRecord.objects.filter(
            senior_citizen__barangay=item, review_status="verified",
            date_of_death__gte=start, date_of_death__lt=end,
        ).count()
        transfers_out = ResidenceTransferRecord.objects.filter(from_barangay=item, transfer_date__gte=start, transfer_date__lt=end).count()
        transfers_in = ResidenceTransferRecord.objects.filter(to_barangay=item, transfer_date__gte=start, transfer_date__lt=end).count()
        booklet_count = BookletReturn.objects.filter(
            senior_citizen__barangay=item, date_returned__gte=start, date_returned__lt=end,
        ).count()
        grocery_count = GroceryClaim.objects.filter(
            senior_citizen__barangay=item, claimed=True,
            distribution__distribution_date__gte=start, distribution__distribution_date__lt=end,
        ).count()
        rows.append([
            item.name,
            seniors.filter(is_active=True).count(),
            seniors.filter(is_active=False).count(),
            pension_count,
            death_count,
            transfers_in,
            transfers_out,
            booklet_count,
            grocery_count,
        ])
    return rows, start, end


def _build_pdf(title, month_label, scope, headers, rows, note, preparer_name):
    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size, rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=22 * mm, bottomMargin=18 * mm,
        title=title, author="OSCA Carmen - Arkheion",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#063b32"), alignment=TA_LEFT, spaceAfter=5))
    styles.add(ParagraphStyle(name="ReportMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#4b5563"), spaceAfter=3))
    styles.add(ParagraphStyle(name="ReportNote", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#374151"), borderColor=colors.HexColor("#b7dfd3"), borderWidth=0.5, borderPadding=7, backColor=colors.HexColor("#eff9f5"), spaceBefore=8, spaceAfter=10))
    styles.add(ParagraphStyle(name="Cell", parent=styles["Normal"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#17212b")))
    styles.add(ParagraphStyle(name="HeaderCell", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.white))
    story = [Paragraph("OSCA CARMEN | SENIOR CITIZEN WELFARE RECORDS", ParagraphStyle("Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#063b32"))), Spacer(1, 4), Paragraph(title, styles["ReportTitle"]), Paragraph(f"Reporting period: {escape(month_label)}", styles["ReportMeta"]), Paragraph(f"Coverage: {escape(scope)}", styles["ReportMeta"]), Paragraph(f"Generated: {timezone.localtime().strftime('%B %d, %Y at %I:%M %p')}", styles["ReportMeta"]), Paragraph(f"Prepared for printing and manual signature by authorized Head Staff. This PDF is not electronically signed. {escape(note)}", styles["ReportNote"])]
    if not rows:
        story.append(Paragraph("No records matched the selected period and barangay.", styles["ReportMeta"]))
    else:
        data = [[Paragraph(escape(str(value)), styles["HeaderCell"]) for value in headers]]
        data.extend([[Paragraph(escape(str(value if value not in (None, "") else "-")), styles["Cell"]) for value in row] for row in rows])
        available_width = page_size[0] - 28 * mm
        widths = [available_width / len(headers)] * len(headers)
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#07584c")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5df")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f6")]),
        ]))
        story.extend([table, Spacer(1, 8), Paragraph(f"Rows: {len(rows)}", styles["ReportMeta"])])

    sign_style = ParagraphStyle("SignField", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#374151"))
    sign_line = Paragraph("________________________________________", sign_style)
    signoff = Table([
        [sign_line, sign_line],
        [Paragraph(escape(preparer_name), ParagraphStyle("PrintedName", parent=sign_style, fontName="Helvetica-Bold")), Paragraph("", sign_style)],
        [Paragraph("Signature over printed name of Head Staff", sign_style), Paragraph("Date signed", sign_style)],
    ], colWidths=[(page_size[0] - 28 * mm) * 0.62, (page_size[0] - 28 * mm) * 0.38], hAlign="LEFT")
    signoff.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(KeepTogether([Spacer(1, 18), Paragraph("MANUAL SIGN-OFF", ParagraphStyle("SignTitle", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#063b32"), spaceAfter=5)), signoff]))

    def draw_page(canvas, document):
        canvas.saveState()
        width, height = page_size
        canvas.setStrokeColor(colors.HexColor("#cbd5df"))
        canvas.line(14 * mm, 13 * mm, width - 14 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(14 * mm, 8 * mm, "Generated from the Arkheion database. Verify figures before submission.")
        canvas.drawRightString(width - 14 * mm, 8 * mm, f"Page {document.page}")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#b9382f"))
        canvas.drawRightString(width - 14 * mm, height - 11 * mm, "PRINT AND SIGN")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


class HeadStaffReportPdfAPIView(APIView):
    permission_classes = [IsAuthenticated, HeadStaffOnly]

    def get(self, request, report_key):
        if report_key not in REPORTS:
            return Response({"detail": "Unknown report type."}, status=404)
        month, barangay, error = _query_filters(request)
        if error:
            return error
        title, label = REPORTS[report_key]
        scope = barangay.name if barangay else "All barangays in Carmen"
        month_label = month.strftime("%B %Y")
        if report_key == "ncsc_annex_a":
            headers = ["OSCA ID", "Senior citizen", "Barangay", "Age", "Date of birth", "Sex", "Registration", "Record status"]
            rows = _senior_rows(report_key, barangay)
            note = "Milestone-age records are a screening list only; verify current eligibility and documentary requirements before filing."
        elif report_key == "masterlist":
            headers = ["OSCA ID", "Senior citizen", "Barangay", "Age", "Date of birth", "Sex", "Registration", "Record status"]
            rows = _senior_rows(report_key, barangay)
            note = "This list reflects database records available at generation time. Confirm current records before submission."
        elif report_key == "pension_payroll":
            headers = ["Period", "OSCA ID", "Senior citizen", "Barangay", "Amount", "Claim status", "Date claimed", "Claimant"]
            rows = _pension_rows(month, barangay)
            note = "This export lists recorded pension claims; it is not proof of eligibility or payment authorization."
        else:
            rows, start, end = _quarterly_rows(month, barangay)
            quarter = (start.month - 1) // 3 + 1
            month_label = f"Q{quarter} {start.year}"
            headers = ["Barangay", "Active seniors", "Inactive", "Pension claims", "Verified deaths", "Transfers in", "Transfers out", "Booklets returned", "Grocery claims"]
            note = "Counts are computed from recorded database events. Unverified population totals are not included."

        preparer_name = request.user.get_full_name().strip() or request.user.get_username()
        pdf_bytes = _build_pdf(title, month_label, scope, headers, rows, note, preparer_name)
        slug = re.sub(r"[^A-Za-z0-9-]+", "-", scope).strip("-").lower() or "all-barangays"
        filename = f"{report_key}-{month.strftime('%Y-%m')}-{slug}.pdf"
        AuditLog.objects.create(
            user=request.user,
            action="export",
            module="report_export",
            description=f"Generated {label}; period={month_label}; scope={scope}; rows={len(rows)}.",
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "private, no-store"
        return response


class HeadStaffReportHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated, HeadStaffOnly]

    def get(self, request):
        entries = AuditLog.objects.filter(module="report_export").select_related("user").order_by("-timestamp")[:100]
        return Response([{
            "id": entry.pk,
            "timestamp": entry.timestamp,
            "username": entry.user.get_username() if entry.user else "Deleted user",
            "staff_name": (entry.user.get_full_name().strip() or entry.user.get_username()) if entry.user else "Deleted user",
            "description": entry.description,
        } for entry in entries])
