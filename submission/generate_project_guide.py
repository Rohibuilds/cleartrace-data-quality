from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "ClearTrace_Project_Guide_and_Judge_QA.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#10233D")
INK = colors.HexColor("#172B45")
MUTED = colors.HexColor("#5A6C80")
TEAL = colors.HexColor("#168A80")
PALE = colors.HexColor("#EFF6F6")
PALE_BLUE = colors.HexColor("#F1F5FA")
LINE = colors.HexColor("#D8E1EA")
AMBER = colors.HexColor("#986316")
PALE_AMBER = colors.HexColor("#FFF6E8")
WHITE = colors.white

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitleCT", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=34, leading=39, textColor=WHITE, alignment=TA_LEFT, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverSubCT", parent=styles["Normal"], fontName="Helvetica", fontSize=13, leading=20, textColor=colors.HexColor("#D5E5EF"), spaceAfter=8))
styles.add(ParagraphStyle(name="KickerCT", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=TEAL, tracking=1.1, spaceAfter=8))
styles.add(ParagraphStyle(name="H1CT", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=NAVY, spaceBefore=2, spaceAfter=12, keepWithNext=True))
styles.add(ParagraphStyle(name="H2CT", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=INK, spaceBefore=9, spaceAfter=6, keepWithNext=True))
styles.add(ParagraphStyle(name="BodyCT", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=14, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name="SmallCT", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.7, leading=11, textColor=MUTED, spaceAfter=4))
styles.add(ParagraphStyle(name="BulletCT", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13.4, textColor=INK, leftIndent=12, firstLineIndent=-8, bulletIndent=0, spaceAfter=4))
styles.add(ParagraphStyle(name="TableHeadCT", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=WHITE))
styles.add(ParagraphStyle(name="TableCT", parent=styles["Normal"], fontName="Helvetica", fontSize=7.8, leading=11, textColor=INK))
styles.add(ParagraphStyle(name="CalloutCT", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=14, textColor=NAVY, spaceAfter=0))
styles.add(ParagraphStyle(name="QuestionCT", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=NAVY, spaceBefore=6, spaceAfter=3, keepWithNext=True))
styles.add(ParagraphStyle(name="AnswerCT", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7, leading=12.5, textColor=INK, leftIndent=10, borderColor=LINE, borderWidth=0, spaceAfter=6))
styles.add(ParagraphStyle(name="LabelCT", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MUTED))


def P(text, style="BodyCT"):
    return Paragraph(text, styles[style])


def bullets(items):
    return [P(f"&#8226; {item}", "BulletCT") for item in items]


def callout(title, body, background=PALE):
    box = Table([[P(title, "CalloutCT")], [P(body, "BodyCT")]], colWidths=[168 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL if background == PALE else AMBER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
    ]))
    return box


def data_table(headers, rows, widths, repeatRows=1):
    data = [[P(str(cell), "TableHeadCT") for cell in headers]]
    data.extend([[P(str(cell), "TableCT") for cell in row] for row in rows])
    table = Table(data, colWidths=widths, repeatRows=repeatRows, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE_BLUE]),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


class GuideDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(str(filename), pagesize=A4, leftMargin=21 * mm, rightMargin=21 * mm,
                         topMargin=20 * mm, bottomMargin=19 * mm, title="ClearTrace Project Guide and Judge Q&A",
                         author="ClearTrace Team", subject="Project, architecture, security, deployment, and judge preparation")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="guide", frames=[frame], onPage=self.decorate)])

    def decorate(self, canvas, doc):
        page = doc.page
        if page == 1:
            return
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(21 * mm, h - 13 * mm, w - 21 * mm, h - 13 * mm)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawString(21 * mm, h - 10.5 * mm, "CLEARTRACE  /  PROJECT GUIDE")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(w - 21 * mm, 10 * mm, f"ClearTrace  |  {page}")
        canvas.restoreState()


story = []

# Cover
story.append(Spacer(1, 9 * mm))
cover = Table([
    [P("CLEARTRACE  /  DATAFIX", "KickerCT")],
    [P("Every issue explained.<br/>Every fix traceable.", "CoverTitleCT")],
    [P("Project guide, technical overview, deployment truth, and judge Q&amp;A", "CoverSubCT")],
    [Spacer(1, 7 * mm)],
    [P("A review-first workspace that detects data quality issues, proposes understandable repairs, and records the human decision before changes are applied.", "CoverSubCT")],
], colWidths=[168 * mm])
cover.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
    ("BOX", (0, 0), (-1, -1), 0, NAVY),
    ("LEFTPADDING", (0, 0), (-1, -1), 18 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 15 * mm),
    ("TOPPADDING", (0, 0), (-1, 0), 18 * mm), ("BOTTOMPADDING", (0, 0), (-1, 0), 4 * mm),
    ("TOPPADDING", (0, 1), (-1, 1), 4 * mm), ("BOTTOMPADDING", (0, 1), (-1, 1), 3 * mm),
    ("TOPPADDING", (0, 2), (-1, 2), 0), ("BOTTOMPADDING", (0, 2), (-1, 2), 8 * mm),
    ("TOPPADDING", (0, 4), (-1, 4), 0), ("BOTTOMPADDING", (0, 4), (-1, 4), 17 * mm),
]))
story.append(cover)
story.append(Spacer(1, 9 * mm))
story.append(P("PROJECT LINKS", "KickerCT"))
story.append(data_table(
    ["Item", "Current reference"],
    [
        ["Team / problem", "ClearTrace / Problem 01 - DataFix: Autonomous Data Quality and Repair Engine"],
        ["Live application", "<link href='https://cleartrace-web-production.up.railway.app/'>cleartrace-web-production.up.railway.app</link>"],
        ["Public source", "<link href='https://github.com/Rohibuilds/cleartrace-data-quality'>github.com/Rohibuilds/cleartrace-data-quality</link>"],
        ["Prepared", "20 November 2026. Status statements below distinguish tested code from configured live services."],
    ], [36 * mm, 132 * mm]
))
story.append(Spacer(1, 7 * mm))
story.append(callout("Read this before the judge demo", "The no-sign-in synthetic sample is available. Real email OTP and owner security-alert delivery require Gmail SMTP credentials that are not configured in the current Railway deployment. Google sign-in also remains off until OAuth credentials are configured. Do not claim those provider-dependent flows are live." , PALE_AMBER))
story.append(Spacer(1, 8 * mm))
story.append(P("Prepared as a practical handoff and presentation reference. Use the public synthetic sample for demonstrations; do not upload confidential customer data to the shared demo service.", "SmallCT"))
story.append(PageBreak())

# 1
story += [P("1. ClearTrace in one minute", "H1CT"),
          P("ClearTrace is a data quality workspace for people who need to clean a dataset without losing context or silently changing records. It scans a CSV, Excel workbook, or supported table-based PDF; explains findings; proposes safe candidate repairs; shows a before/after diff; and applies a change only after a person approves it.")]
story.append(data_table(["Question", "Short answer"], [
    ["Problem", "Data quality problems create unreliable analysis, wasted review time, and hard-to-reproduce fixes."],
    ["Who it helps", "Analysts and small teams reviewing structured or tabular operational data."],
    ["Core principle", "Detection is evidence. A suggestion is not permission. A human approves a repair."],
    ["Outcome", "A reviewed dataset, a re-run scan, revision history, and downloadable evidence."],
], [38 * mm, 130 * mm]))
story += [Spacer(1, 5 * mm), P("The product promise", "H2CT"),
          callout("Inspect → Explain → Propose → Review → Apply → Recheck → Export", "A reviewer can inspect what ClearTrace found, edit a candidate, approve or reject it, and later compare or undo approved changes. This makes the workflow auditable and keeps domain judgment with the user."),
          P("What ClearTrace is not", "H2CT")]
story += bullets([
    "It is not a black-box auto-cleaner that rewrites every unusual value.",
    "It is not a hosted general-purpose AI model that receives uploaded datasets by default.",
    "The public judge preview is not a commercial multi-tenant data service or a certification for regulated information.",
    "The phone experience is an installable web app (PWA), not a native App Store or Play Store binary.",
])
story.append(PageBreak())

# 2
story += [P("2. Product workflow", "H1CT"),
          P("The same core engine supports a guided browser workflow and REST API. A judge can enter through a temporary public workspace with synthetic sample data. A signed-in user gets a persistent identity-based workspace when email delivery is configured.")]
story.append(data_table(["Step", "What happens", "What the reviewer sees"], [
    ["1. Import", "Validate the file, parse supported tables, record source metadata and provenance.", "Dataset name, size, rows, columns, preview, warnings."],
    ["2. Inspect", "Run deterministic quality rules and math validations.", "Finding type, column, row references, severity, explanation."],
    ["3. Explain", "Show the rule and its evidence; retrieve relevant indexed passages for questions.", "Plain-language reason, source references, recommendation."],
    ["4. Propose", "Create non-mutating repair candidates where a safe action is defined.", "Risk, before/after summary, sample cell diffs."],
    ["5. Decide", "Reviewer edits, approves, rejects, or leaves the suggestion pending.", "Explicit controls; no silent edits."],
    ["6. Apply & recheck", "Apply approved work to a working copy, advance revision, rescan.", "Updated score/findings and an audit event."],
    ["7. Trace & export", "Compare revisions, inspect/undo history, export data and reports.", "Cleaned CSV, findings, audit, passport, executive report."],
], [24 * mm, 71 * mm, 73 * mm]))
story += [Spacer(1, 5 * mm), P("A useful judge walkthrough", "H2CT")]
story += bullets([
    "Open the live app and choose the no-sign-in sample workspace.",
    "Show the score and one concrete finding, then open Repair Studio.",
    "Inspect a before/after suggestion; demonstrate one approval or rejection on synthetic data.",
    "Re-run or inspect the revised score, then open the ledger/time machine and show the recorded decision.",
    "Show the export/passport and mobile navigation. State that account OTP is not configured on this deployment.",
])
story.append(PageBreak())

# 3
story += [P("3. System architecture", "H1CT"),
          P("The deployed experience is one HTTPS service: a responsive JavaScript PWA is served alongside a Python FastAPI API. The rules engine and session operations are implemented in Python and Pandas. The Streamlit entry points are retained as companion/earlier interfaces; Railway's public app is the FastAPI + PWA service.")]
arch = Table([
    [P("PHONE / DESKTOP BROWSER", "TableHeadCT")],
    [P("Responsive PWA · navigation · review controls · install metadata", "TableCT")],
    [P("HTTPS / same origin", "LabelCT")],
    [P("FASTAPI SERVICE  /  server.py", "TableHeadCT")],
    [P("Auth gate · security headers · request limits · API routes · static app", "TableCT")],
    [P("QUALITY ENGINE  /  cleartrace/", "TableHeadCT")],
    [P("Ingest · scan · math · repair · audit · scoring · retrieval · export", "TableCT")],
    [P("PERSISTENCE  /  configured data directory", "TableHeadCT")],
    [P("AES-GCM encrypted workspace snapshots · SQLite auth state · protected key material", "TableCT")],
], colWidths=[168 * mm])
arch.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("BACKGROUND", (0, 2), (-1, 2), PALE),
    ("BACKGROUND", (0, 3), (-1, 3), NAVY),
    ("BACKGROUND", (0, 5), (-1, 5), NAVY),
    ("BACKGROUND", (0, 7), (-1, 7), NAVY),
    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
    ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
]))
story += [arch, Spacer(1, 5 * mm), P("Main code areas", "H2CT")]
story.append(data_table(["Area", "Files", "Purpose"], [
    ["Browser app", "static/index.html, static/app.js, static/cleartrace.css, static/sw.js", "PWA shell and interactive modules."],
    ["API & middleware", "server.py", "Session/access checks, endpoints, request protections, static routes."],
    ["Data engine", "cleartrace/ingest.py, scan.py, scoring.py, math_engine.py", "Input bounds, detection, score, arithmetic validation."],
    ["Change lifecycle", "cleartrace/repair.py, audit.py, timemachine.py", "Proposals, explicit apply, revisions, undo/restore."],
    ["Trust & support", "cleartrace/persistence.py, auth.py, passport.py, retrieval.py, export.py", "Encryption, login, provenance, evidence retrieval, exports."],
], [30 * mm, 72 * mm, 66 * mm]))
story.append(PageBreak())

# 4
story += [P("4. Detection and scoring", "H1CT"),
          P("The core quality detectors are deterministic rules. They are designed to show candidate issues, not infer business truth that is not present in the file.")]
story.append(data_table(["Detector", "How it works", "Caution"], [
    ["Missing values", "Flags nulls, empty strings, and whitespace-only cells.", "Does not invent a replacement value."],
    ["Exact duplicates", "Compares complete rows and flags later copies.", "A repeat can be legitimate; confirm before removal."],
    ["Outer whitespace", "Finds leading/trailing spaces in text values.", "Trimming does not normalize interior text."],
    ["Category variants", "Groups case-folded text and suggests the most frequent observed variant.", "Frequency is a heuristic; domain canonicalization may differ."],
    ["Invalid dates", "Infers likely date columns and flags unparsable values.", "Date locale/schema may require domain context."],
    ["Invalid numbers", "Infers likely numeric columns and flags non-numeric entries.", "A non-number string can be valid in some schemas."],
    ["Potential outliers", "Uses the 1.5 × IQR fence when enough numeric observations exist.", "An outlier is a review signal, not proof of error."],
], [34 * mm, 82 * mm, 52 * mm]))
story += [Spacer(1, 5 * mm), P("Transparent score", "H2CT"),
          P("The score is a deterministic weighted summary of four dimensions. It is a prioritization aid, not a universal statistical certification.")]
story.append(data_table(["Component", "Weight", "Defect signal"], [
    ["Completeness", "35%", "Missing cells / total cells"],
    ["Uniqueness", "25%", "Exact duplicate rows / total rows"],
    ["Structural validity", "25%", "Invalid date and invalid numeric findings / total cells"],
    ["Consistency", "15%", "Whitespace and category-variant findings / total cells"],
], [43 * mm, 25 * mm, 100 * mm]))
story += [Spacer(1, 4 * mm), P("For the current public sample the verified score endpoint returned 93.8 / 100 (Grade A). Scores change as the reviewer applies or rejects candidate work and rescans. The denominator and rule definitions are shown in the code and UI; a score should be interpreted alongside the findings.", "BodyCT"),
          callout("Why not one opaque AI score?", "A clear formula makes the quality summary explainable and repeatable. The score does not claim to know whether a rare value is invalid; the finding remains available for review.")]
story.append(PageBreak())

# 5
story += [P("5. Repair, revision, and audit", "H1CT"),
          P("A repair begins as a candidate object. It is distinct from a data mutation. The UI presents an explanation and sample diffs, then sends an explicit decision to the API.")]
story.append(data_table(["Control", "Effect"], [
    ["Edit", "Changes the proposed value/action before approval where the workflow supports editing."],
    ["Approve / apply", "Applies the approved operation to the working copy, advances the revision, and records before/after context."],
    ["Reject", "Records the reviewer decision without applying the proposed mutation."],
    ["Rescan", "Runs the same quality checks on the current revision."],
    ["Compare", "Shows revision-level quality and change differences."],
    ["Undo / restore", "Reverts a prior approved change or returns to a prior snapshot through a new recorded operation."],
], [43 * mm, 125 * mm]))
story += [Spacer(1, 5 * mm), P("Audit record", "H2CT"),
          P("Audit events carry a timestamp, action/decision, rule, target columns and rows, revision before and after, short before/after summaries, reason, item count, and an undo reference where applicable. The project supports a downloadable audit CSV and revision history. Treat this as an application audit trail; it is not a separately administered immutable compliance archive.")]
story += [P("Export and evidence", "H2CT")]
story.append(data_table(["Export", "Contents / use"], [
    ["Cleaned CSV", "Current working dataset. Export sanitization protects spreadsheet formula-like text."],
    ["Findings CSV", "Detected issue groups and their locations/metadata."],
    ["Audit CSV", "Recorded session decisions and mutations."],
    ["Data Passport", "Dataset fingerprint and summary metadata to help identify an artifact revision."],
    ["Executive report", "Readable summary, score progression and quality context."],
], [42 * mm, 126 * mm]))
story.append(PageBreak())

# 6
story += [P("6. Math intelligence and evidence assistant", "H1CT"),
          P("ClearTrace includes a separate invoice/math validation path. It uses Decimal arithmetic and explicit tolerances for currency-like comparisons, and can check formula relationships and constraints. The evaluator is not an LLM and does not ask a language model to calculate totals.")]
story.append(data_table(["Capability", "What it does", "Guardrail"], [
    ["Invoice math checks", "Compare observed amounts against expected formulas using decimal arithmetic and a defined tolerance.", "Calculation steps and discrepancy values are inspectable."],
    ["Constraints", "Check conditions such as non-negative values, discount ceilings, and configured relationships.", "Rules can be inspected and managed through the app/API."],
    ["Math proposals", "Convert eligible mathematical findings into candidate repairs.", "Applying a suggested value still requires review."],
    ["Evidence search", "Builds a local session index of schema context, rules, and findings; ranks passages with BM25-style retrieval.", "Returned passages include references to supporting evidence."],
    ["Optional local LLM", "Can be explicitly enabled for local Ollama inference; disabled by default.", "No hosted model receives dataset content by default; model output is read-only and citations are checked."],
], [34 * mm, 73 * mm, 61 * mm]))
story += [Spacer(1, 5 * mm), callout("A truthful answer to 'Is this AI?'", "The main detection, arithmetic, ranking, scoring, and repair policy are deterministic. The assistant can retrieve evidence and may use an explicitly opted-in local Ollama model, but the current hosted demo reports a direct-evidence fallback. It does not silently approve a repair or fabricate a model as active."),
          P("This separation is a deliberate design choice: arithmetic accuracy and destructive changes stay in deterministic, inspectable code; language assistance can explain retrieved evidence but does not control data mutation.", "BodyCT")]
story.append(PageBreak())

# 7
story += [P("7. Identity, security, and privacy", "H1CT"),
          P("Security protections are layered, but this deployment is still a controlled demo. The measures below describe code behavior; provider-dependent features are only operational when their secrets and infrastructure are configured.")]
story.append(data_table(["Area", "Implemented behavior", "Live status / boundary"], [
    ["Email OTP", "Six-digit single-use code; ten-minute expiry; bounded attempts and request cooldown/rate limits; opaque server-side session token stored as a digest.", "Code exists, but email delivery is unavailable until Gmail SMTP is configured."],
    ["Cookies", "HttpOnly, SameSite=Lax; Secure on HTTPS; revocable session records; 30-day auth session expiry.", "Depends on persistent storage for continuity across service restarts."],
    ["Owner alerts", "Code sends owner notices on successful sign-in and repeated invalid-code attempts when SMTP is configured.", "Not verified live; uses the same missing SMTP credentials."],
    ["Google OIDC", "Optional state-bound flow; verifies token signature, issuer, audience, expiry, and verified email.", "Disabled until Google OAuth client ID/secret and redirect are configured."],
    ["Roles", "Owner/admin/analyst/viewer policies; viewer mutation restrictions; one owner-managed organization workspace.", "Code is deployed; live exercise needs working sign-in. Assigned members share org data."],
    ["Stored workspace", "AES-256-GCM authenticated encryption for persisted workspace snapshots; session identity bound as AAD; restricted key files or environment key.", "Requires persistent volume and durable key management. Encryption does not replace authorization/backups."],
    ["HTTP/browser", "Same-origin API, security headers, CSRF/origin checks, request-size bounds, upload validation, rate-limiting middleware.", "Not an independent penetration test or security certification."],
    ["Public preview", "Temporary isolated synthetic judge workspace; sample can be repaired; uploads blocked; expires after eight hours.", "Available without sign-in; do not place private data in it."],
], [27 * mm, 78 * mm, 63 * mm]))
story += [Spacer(1, 4 * mm), callout("Data use in the public preview", "The judge path uses synthetic sample data. The app's stated design is session-oriented and does not intentionally send uploaded dataset contents to third-party AI services. Use synthetic data for public demos; do not treat the hosted preview as an approved confidential-data environment.", PALE_AMBER)]
story.append(PageBreak())

# 8
story += [P("8. Phone experience, deployment, and local setup", "H1CT"),
          P("The browser application is responsive and includes install metadata/service-worker shell caching. A user can add the HTTPS PWA to a phone home screen. Offline mode can launch the cached shell; authentication, upload, scan, and export operations require an internet connection.")]
story.append(data_table(["Platform", "How to use it"], [
    ["iPhone / iPad", "Open the HTTPS URL in Safari → Share → Add to Home Screen."],
    ["Android", "Open the HTTPS URL in Chrome → browser menu → Install app / Add to Home screen."],
    ["Desktop", "Open the same URL in a modern browser. Responsive layout adapts module navigation."],
    ["Public deployment", "Railway container service, HTTPS domain, health probe at /health."],
], [42 * mm, 126 * mm]))
story += [Spacer(1, 5 * mm), P("Run the project locally", "H2CT"),
          P("Requirements: Python 3.10+ is recommended by the README. The recorded verification environment used Python 3.9.6. Run from the repository root:", "BodyCT")]
code = "git clone https://github.com/Rohibuilds/cleartrace-data-quality.git<br/>cd cleartrace-data-quality<br/>python3 -m venv .venv<br/>source .venv/bin/activate<br/>python -m pip install -r requirements.txt<br/>python run.py"
codebox = Table([[Paragraph(code, ParagraphStyle("CodeCT", fontName="Courier", fontSize=8.2, leading=13, textColor=colors.HexColor("#E8F0F8"))) ]], colWidths=[168 * mm])
codebox.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("BOX", (0, 0), (-1, -1), 0.5, NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
story += [codebox, Spacer(1, 4 * mm), P("For the companion Streamlit interface, run `python run.py --streamlit`. For OTP locally, configure the SMTP environment variables in a shell/secret manager. Never put Gmail app passwords, OAuth secrets, or encryption keys in source control or a chat.", "BodyCT"),
          P("Important Railway settings", "H2CT")]
story += bullets([
    "Attach the persistent volume at /data and set CLEARTRACE_DATA_DIR=/data.",
    "Set CLEARTRACE_MASTER_KEY to a securely generated key and back it up through a managed process.",
    "For email OTP/alerts, set SMTP username, app password, sender, and owner email in Railway Variables, then deploy and send a real test email.",
    "For Google login, configure a Google web OAuth client and register the callback URL shown in DEPLOYMENT.md.",
])
story.append(PageBreak())

# 9
story += [P("9. Current release and known limits", "H1CT"),
          P("The current source revision 2632d3d passed 80 automated tests (20 November 2026). It is deployed to Railway as v2.3.2 in deployment 53f85fd7-c0ac-4a5b-88e1-3a49e06093c4, reported SUCCESS. Live checks found /health healthy, the no-login synthetic sample available with a score of 93.8 / 100, and the updated login/PWA assets present.")]
story.append(data_table(["Status", "Detail"], [
    ["Verified source checks", "80 tests passing after the login setup feedback change; JavaScript syntax and diff checks pass; Bandit found no enabled issues in server.py and auth.py (one intentional 0.0.0.0 bind warning)."],
    ["Live release", "Railway deployment 53f85fd7 reports success at v2.3.2; /health is healthy; the sample workspace returns 93.8/A; protected APIs require a session."],
    ["OTP/owner alerts", "Not working live until SMTP settings including CLEARTRACE_SMTP_PASSWORD are present and a real email is delivered. The mobile screenshot showed the resulting send failure."],
    ["Fix deployed", "API reports mail setup unavailable before attempting OTP; login UI displays the state, disables the unavailable email action, and points users to the no-login sample. PWA cache version is advanced to refresh mobile users."],
    ["Google sign-in", "Optional; no live OAuth credentials, so disabled/not verified."],
    ["Not included", "SAML, SCIM, multi-organization tenancy, formal compliance certification, independent security audit, SMS alerts, native iOS/Android binaries."],
    ["Production readiness", "For a real customer rollout add shared/managed session storage, tested backup and key rotation/recovery, retention/deletion controls, monitoring, stricter abuse throttles, tenant policy controls, and an independent security review."],
], [37 * mm, 131 * mm]))
story += [Spacer(1, 5 * mm), callout("The exact screenshot diagnosis", "The phone form reached the OTP endpoint and the endpoint returned its generic mail-delivery failure. The previously verified Railway status showed smtp_delivery_enabled=false because CLEARTRACE_SMTP_PASSWORD was missing. The code cannot send an email until the app password is set privately in Railway Variables. The UI/API change makes this setup state explicit; it does not create or guess an email credential.", PALE_AMBER)]
story.append(PageBreak())

# 10
story += [P("10. Judge questions and suggested answers", "H1CT"),
          P("Use these answers as a reference, not a memorized script. Be precise about what is live versus what requires operator configuration.")]
qa1 = [
    ("1. What problem does ClearTrace solve?", "It helps teams discover data issues, understand why a value is flagged, review safe repair candidates, and keep a traceable record of decisions. It reduces hidden cleanup and makes repeatable review easier."),
    ("2. What is the main difference from a normal cleaning script?", "A script often applies transformations in bulk. ClearTrace separates findings from mutations, shows the proposed before/after change, and waits for an explicit reviewer decision."),
    ("3. How does the app detect issues?", "The current engine uses deterministic checks for missing values, duplicate rows, outer whitespace, category variants, invalid dates, invalid numeric values, potential IQR outliers, and invoice/math rules."),
    ("4. Why is an outlier not automatically removed?", "An outlier can be a valid rare event. ClearTrace flags it as evidence for investigation; it does not equate statistical rarity with a data error."),
    ("5. How is the score calculated?", "It is a weighted score: completeness 35%, uniqueness 25%, structural validity 25%, and consistency 15%. The score is transparent and should be read with its findings, not treated as a universal certification."),
    ("6. Does ClearTrace use AI?", "The core scanning, math, scoring, and repair policy are deterministic. Evidence retrieval is local. An optional local Ollama model can be explicitly enabled, but it is disabled in the current hosted demo; the demo returns direct retrieved evidence rather than claiming an active hosted AI."),
    ("7. Can an AI change the dataset?", "No. Any language-model component is read-only. Data mutation goes through explicit application repair actions and human approval."),
    ("8. How do you avoid inventing missing data?", "Missing cells are flagged with a recommendation to check the source or supply a domain-approved value. The system does not fabricate a replacement."),
    ("9. What happens after approval?", "The working revision changes, an audit event is added, and the dataset can be rescanned. The user can compare versions and use undo/history features."),
]
for q, a in qa1:
    story.append(KeepTogether([P(q, "QuestionCT"), P(a, "AnswerCT")]))
story.append(PageBreak())

# 11
story += [P("11. Judge questions and suggested answers (continued)", "H1CT")]
qa2 = [
    ("10. What file types are supported?", "The API ingests CSV and XLSX, and supported text-table PDF workflows. The exact path is size-bounded. Legacy XLS and macro-containing workbooks are rejected. The UI and current deployment should be used for the final supported-format demo."),
    ("11. Where does the uploaded data go?", "The app is designed for session-oriented processing and does not intentionally send dataset contents to third-party AI services. For a public demo, use the built-in synthetic data. Do not upload confidential or regulated data to the shared Railway demo."),
    ("12. Is data encrypted?", "Persisted workspace snapshots use AES-256-GCM authenticated encryption in the code. Proper security still depends on a durable key, persistent volume, access controls, backups, and operational key management; this is not a claim of end-to-end encryption or a certification."),
    ("13. Can judges try it without an account?", "Yes. Choose 'Explore sample workspace' to enter an isolated temporary workspace loaded with synthetic data. Upload is blocked in that judge session."),
    ("14. Why did email OTP fail in the screenshot?", "Outbound Gmail SMTP was not configured because the Railway app password variable was absent in the latest verification. The source now reports that setup state clearly and directs visitors to the judge sample. Real personal sign-in requires the owner to configure SMTP and test delivery."),
    ("15. Are owner email alerts working?", "The code sends sign-in and repeated-failure notices when mail is configured. They are not live-verified in the current deployment because the same SMTP password is missing."),
    ("16. Is Google sign-in enabled?", "Google OIDC is optional in the code, but it is off until the OAuth client ID, secret, public URL, and matching callback are configured. It has not been live-tested in this deployment."),
    ("17. Can a team share a workspace?", "The code supports one owner-managed organization workspace with owner/admin/analyst/viewer roles. Members assigned to that organization share its datasets under role limits. It does not support multiple organizations, SAML, or SCIM."),
    ("18. Is this a phone app?", "It is a responsive installable PWA, so it can be added to an iPhone or Android home screen. It is not a native app-store build. Online data operations still need a network connection."),
    ("19. How was it tested?", "The updated source passes 80 automated tests, including API, adversarial input, persistence encryption, role restrictions, OTP behavior with mocked mail, math rules, and deployment middleware. Mock SMTP tests verify code behavior but do not prove Gmail delivery."),
    ("20. What would you build next for production?", "Configure and verify a real mail provider, use managed identity or strong organizational SSO, add multi-tenant policy boundaries, shared bounded session storage, monitored rate limits, tested recovery/retention, and independent security review."),
]
for q, a in qa2:
    story.append(KeepTogether([P(q, "QuestionCT"), P(a, "AnswerCT")]))
story.append(PageBreak())

# 12
story += [P("12. Submission and handoff checklist", "H1CT"),
          P("A good demo is short, honest, and built around one complete review. Start from the public sample, show the finding, approve one safe repair, then prove the result through a recheck and trace record.")]
story.append(data_table(["Submission field", "Known value / action"], [
    ["Team name", "ClearTrace"],
    ["Problem statement", "Problem 01 - DataFix: Autonomous Data Quality and Repair Engine."],
    ["Public GitHub", "<link href='https://github.com/Rohibuilds/cleartrace-data-quality'>Rohibuilds/cleartrace-data-quality</link>"],
    ["Deployed app", "<link href='https://cleartrace-web-production.up.railway.app/'>cleartrace-web-production.up.railway.app</link>"],
    ["PDF link", "Upload this final PDF to the team's shared Drive folder if a Drive link is required by the submission form."],
    ["LinkedIn demo video", "No finished screen recording was created in the latest attempt. Record and check the public link; keep it under three minutes."],
], [43 * mm, 125 * mm]))
story += [Spacer(1, 6 * mm), P("Suggested closing", "H2CT"),
          callout("ClearTrace", "Turns data cleanup into a reviewable process: identify the issue, inspect the evidence, approve the repair, and keep the trace."),
          Spacer(1, 6 * mm), P("Project references", "H2CT")]
story += bullets([
    "README.md - setup, feature overview, and repository map.",
    "SECURITY.md - deployment boundaries, authentication, encryption, and operational gaps.",
    "DEPLOYMENT.md - Railway environment variables and deployment runbook.",
    "TEST_REPORT.md - test results and the boundary between mocked provider tests and live verification.",
    "submission/VIDEO_SCRIPT.md - timed demo outline and recording checklist.",
])
story.append(Spacer(1, 5 * mm))
story.append(HRFlowable(width="100%", thickness=0.8, color=LINE))
story.append(Spacer(1, 3 * mm))
story.append(P("ClearTrace  |  Project guide prepared 20 November 2026  |  Use the live app and current repository state as the source of truth for any later release changes.", "SmallCT"))

GuideDoc(OUT).build(story)
print(OUT)
