import streamlit as st
import sqlite3
import json
import hashlib
import re
import io
from datetime import datetime, date
from pathlib import Path

import fitz
import pytesseract
from PIL import Image
from student_validation import validate_student_data
from field_extractor import extract_student_fields

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "smartverify.db"
UPLOAD_DIR = APP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Update this path if Tesseract is installed in a different folder.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

st.set_page_config(page_title="AICTE SmartVerify", page_icon="🛡️", layout="wide")


def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            institution TEXT NOT NULL,
            institution_code TEXT,
            category TEXT NOT NULL,
            submitted_by TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Submitted'
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            extracted_text TEXT,
            sha256 TEXT,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            document_id INTEGER,
            rule_code TEXT NOT NULL,
            status TEXT NOT NULL,
            explanation TEXT NOT NULL,
            evidence TEXT,
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TEXT NOT NULL
        )""")


init_db()


def audit(app_id, action, details=""):
    with db() as con:
        con.execute(
            "INSERT INTO audit_logs(application_id,action,details,timestamp) VALUES(?,?,?,?)",
            (app_id, action, details, datetime.now().isoformat(timespec="seconds")),
        )


def extract_pdf_text(data):
    """Extract selectable text from a digital PDF."""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc).strip()
    except Exception:
        return ""


def extract_document_text(data, filename):
    """Extract text from digital PDFs, scanned PDFs, and common image files."""
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            # Prefer embedded/selectable text when available.
            text = extract_pdf_text(data)
            if text.strip():
                return text

            # If no selectable text is present, OCR each scanned PDF page.
            pages_text = []
            with fitz.open(stream=data, filetype="pdf") as pdf:
                for page in pdf:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes("png")))
                    pages_text.append(pytesseract.image_to_string(image))
            return "\n".join(pages_text).strip()

        if name.endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(io.BytesIO(data))
            return pytesseract.image_to_string(image).strip()

    except Exception as e:
        st.warning(f"Text extraction failed for {filename}: {e}")

    return ""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def classify_doc(filename):
    s = filename.lower()
    if "noc" in s or "no_objection" in s:
        return "NOC / Permission"
    if "affidavit" in s or "undertaking" in s:
        return "Affidavit / Undertaking"
    if "accredit" in s or "naac" in s or "nba" in s:
        return "Accreditation / Certification"
    if "faculty" in s or "staff" in s:
        return "Faculty Record"
    if "infra" in s or "building" in s or "floor" in s:
        return "Infrastructure Evidence"
    if "approval" in s or "eoa" in s:
        return "Previous Approval"
    if "certificate" in s or "cert" in s:
        return "Certificate"
    return "Other / Unclassified"


def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def run_validation(app_id):
    with db() as con:
        app = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        docs = con.execute(
            "SELECT * FROM documents WHERE application_id=?", (app_id,)
        ).fetchall()
        con.execute("DELETE FROM findings WHERE application_id=?", (app_id,))
        now = datetime.now().isoformat(timespec="seconds")
        findings = []
        present_types = {d["doc_type"] for d in docs}

        # Demo checklist: confirm actual requirements for the selected category.
        required = ["Affidavit / Undertaking", "NOC / Permission", "Previous Approval"]
        for req in required:
            if req not in present_types:
                findings.append((
                    app_id, None, "DOC-REQUIRED", "Missing",
                    f"Expected document type not found: {req}.",
                    "Checklist used: prototype demo checklist. Confirm requirements for the actual application category.",
                ))

        if not docs:
            findings.append((
                app_id, None, "DOC-NONE", "Missing",
                "No documents have been uploaded for this application.",
                "Upload the required supporting files.",
            ))

        all_text = []
        code_pattern = r"(?:institution|college)\s*(?:code|id)\s*[:\-]\s*([A-Za-z0-9\-]+)"
        for d in docs:
            txt = d["extracted_text"] or ""

            if txt.strip():
                fields = extract_student_fields(txt)

                st.write("**Extracted Student Fields**")
                st.json(fields)

                all_text.append((d, txt))
            if not txt.strip():
                findings.append((
                    app_id, d["id"], "OCR-EMPTY", "Manual review",
                    f"No text could be extracted from {d['filename']}.",
                    "Check the file quality and Tesseract installation, or review the document manually.",
                ))

            # Dates are advisory only; not every date is an expiry date.
            date_pattern = r"(?:valid\s*(?:until|upto|up to)|expiry\s*date|expires\s*on)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})"
            for match in re.finditer(date_pattern, txt, re.I):
                dt = parse_date(match.group(1))
                if dt and dt < date.today():
                    findings.append((
                        app_id, d["id"], "CERT-EXPIRED", "Expired",
                        f"Possible expired validity date in {d['filename']}: {dt.isoformat()}.",
                        f"Matched text: {match.group(0)}. Confirm that this is the governing expiry date.",
                    ))

        # Compare institution codes across uploaded documents (basic heuristic).
        codes = {}
        for d, txt in all_text:
            m = re.search(code_pattern, txt, re.I)
            if m:
                codes.setdefault(m.group(1).upper(), []).append(d["filename"])
        if len(codes) > 1:
            details = "; ".join(f"{code}: {', '.join(names)}" for code, names in codes.items())
            findings.append((
                app_id, None, "CROSS-DOC-CODE", "Mismatch",
                "Different institution codes were found across uploaded documents.",
                details,
            ))

        # Exact duplicate upload detection by hash.
        hashes = {}
        for d in docs:
            if d["sha256"]:
                hashes.setdefault(d["sha256"], []).append(d["filename"])
        for names in hashes.values():
            if len(names) > 1:
                findings.append((
                    app_id, None, "DUPLICATE-FILE", "Review",
                    "Identical file content was uploaded more than once.",
                    ", ".join(names),
                ))

        if not findings:
            findings.append((
                app_id, None, "CHECKS-COMPLETE", "Passed",
                "No issues were identified by the configured prototype checks.",
                "This is not an approval decision or proof that every document is authentic.",
            ))

        con.executemany(
            """INSERT INTO findings(application_id,document_id,rule_code,status,explanation,evidence,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            [(a, b, c, d, e, f, now) for a, b, c, d, e, f in findings],
        )
        needs_review = any(
            item[3] in ("Missing", "Expired", "Mismatch", "Manual review", "Review")
            for item in findings
        )
        con.execute(
            "UPDATE applications SET status=? WHERE id=?",
            ("Review required" if needs_review else "Checks complete", app_id),
        )

    audit(app_id, "Validation run", f"{len(findings)} finding(s) generated")
    return len(findings)


def status_badge(status):
    colors = {
        "Passed": "🟢", "Missing": "🔴", "Expired": "🔴", "Mismatch": "🟠",
        "Manual review": "🟠", "Review": "🟠", "Verified (demo)": "🟢",
        "Mismatch (demo)": "🟠", "Pending": "🟡", "Unavailable": "⚪",
    }
    return f"{colors.get(status, '🔵')} {status}"





st.markdown("""
<style>

/* Main headings */
h1 {
    font-size: 40px !important;
}
h2 {
    font-size: 32px !important;
}
h3 {
    font-size: 27px !important;
}

/* Sidebar navigation */
section[data-testid="stSidebar"] [role="radiogroup"] label p {
    font-size: 18px !important;
    font-weight: 500;
}
section[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: 13px 14px;
    min-height: 50px;
}

/* Summary card labels and numbers */
[data-testid="stMetricLabel"] p {
    font-size: 18px !important;
}
[data-testid="stMetricValue"] {
    font-size: 34px !important;
    font-weight: 700;
}
[data-testid="stMetric"] {
    padding: 20px;
    min-height: 125px;
}

/* Table font */
[data-testid="stDataFrame"] {
    font-size: 16px;
}

/* Normal text, labels and inputs */
.stMarkdown p,
.stCaption,
.stTextInput label,
.stSelectbox label,
.stFileUploader label {
    font-size: 17px;
}
.stButton > button {
    font-size: 16px;
    padding: 9px 16px;
}

/* Main and sidebar backgrounds */
.stApp,
section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
}

section[data-testid="stSidebar"] {
    border-right: 1px solid #D9EED5;
}

section[data-testid="stSidebar"] > div {
    padding: 1.5rem 1rem;
}

/* Sidebar navigation spacing */
section[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 6px;
}

/* Hide radio circles */
section[data-testid="stSidebar"] [role="radio"] {
    display: none;
}

/* Navigation items */
section[data-testid="stSidebar"] [role="radiogroup"] label {
    background-color: #FFFFFF;
    padding: 11px 12px;
    border-radius: 9px;
    margin-bottom: 4px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: background-color 0.2s ease;
}

/* Navigation text */
section[data-testid="stSidebar"] [role="radiogroup"] label p {
    font-size: 14px;
    font-weight: 500;
}

/* Selected and hover states */
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked),
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background-color: #D9EED5;
    border-color: #D9EED5;
}

/* Metric cards */
[data-testid="stMetric"] {
    background-color: #D9EED5;
    border: 1px solid #D9EED5;
    border-radius: 10px;
    padding: 14px;
}

/* Buttons */
.stButton > button {
    background-color: #D9EED5;
    border: 1px solid #D9EED5;
    border-radius: 8px;
}

/* Tables */
[data-testid="stDataFrame"] {
    border: 1px solid #D9EED5;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)



st.title("🛡️ SmartVerify")
st.caption("AI-powered application validation and document authentication — demonstration prototype")

pages = [
    "Overview",
    "Create application",
    "Upload documents",
    "Validate & review",
    "Student Data Validation",
    "Audit history"
]
page = st.sidebar.radio("Navigation", pages)
with db() as con:
    applications = con.execute("SELECT * FROM applications ORDER BY id DESC").fetchall()


if page == "Overview":
    with db() as con:
        total = con.execute(
            "SELECT COUNT(*) n FROM applications"
        ).fetchone()["n"]

        docs_n = con.execute(
            "SELECT COUNT(*) n FROM documents"
        ).fetchone()["n"]

        findings_n = con.execute(
            "SELECT COUNT(*) n FROM findings WHERE status != 'Passed'"
        ).fetchone()["n"]

        review_n = con.execute(
            "SELECT COUNT(*) n FROM applications "
            "WHERE status = 'Review required'"
        ).fetchone()["n"]

    st.subheader("Validation overview")

    a, b, c, d = st.columns(4)
    a.metric("Applications", total)
    b.metric("Documents", docs_n)
    c.metric("Findings", findings_n)
    d.metric("Needs review", review_n)

    st.markdown("<div style='height:16px'></div>",
                unsafe_allow_html=True)

    st.subheader("Recent applications")

    if applications:
        rows = []
        for item in applications[:8]:
            created = item["created_at"]
            try:
                created = datetime.fromisoformat(
                    created
                ).strftime("%d %b, %I:%M %p")
            except (ValueError, TypeError):
                pass

            rows.append({
                "ID": item["id"],
                "Institution": item["institution"],
                "Category": item["category"],
                "Created": created,
                "Status": item["status"]
            })

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            height=min(360, 45 + len(rows) * 42)
        )
    else:
        st.info(
            "No applications yet. Select Create application "
            "from the sidebar to get started."
        )

    st.markdown("<div style='height:12px'></div>",
                unsafe_allow_html=True)

    st.subheader("Demo sequence")

    steps = [
        ("1", "Create application"),
        ("2", "Upload documents"),
        ("3", "Run validation"),
        ("4", "Review findings")
    ]

    cols = st.columns(4)

    for col, (number, title) in zip(cols, steps):
        with col:
            st.markdown(f"""
            <div style="background:white; border:1px solid #CDE6D6;
                        border-radius:13px; padding:18px 16px;
                        min-height:105px;">
                <div style="background:#2D9D5B;color:white;
                            width:34px;height:34px;border-radius:50%;
                            text-align:center;line-height:34px;
                            font-weight:700;margin-bottom:12px;">
                    {number}
                </div>
                <div style="font-size:15px;color:#294A36;
                            font-weight:600;">
                    {title}
                </div>
            </div>
            """, unsafe_allow_html=True)


elif page == "Create application":
    st.subheader("Create an application")
    with st.form("create_app"):
        institution = st.text_input("Institution name", placeholder="Example: Sunrise Institute of Technology")
        code = st.text_input("Institution code / ID", placeholder="Example: DEMO-102")
        category = st.selectbox("Application category", [
            "Extension of Approval (EoA)", "New programme / course", "Change in intake",
            "Institutional details update", "Other approval-related change",
        ])
        submitted_by = st.text_input("Submitted by", placeholder="Demo user")
        submitted = st.form_submit_button("Create application", type="primary")
    if submitted:
        if not institution.strip():
            st.error("Enter an institution name.")
        else:
            with db() as con:
                cur = con.execute(
                    "INSERT INTO applications(institution,institution_code,category,submitted_by,created_at,status) VALUES(?,?,?,?,?,?)",
                    (institution.strip(), code.strip(), category, submitted_by.strip(), datetime.now().isoformat(timespec="seconds"), "Submitted"),
                )
                app_id = cur.lastrowid
            audit(app_id, "Application created", institution.strip())
            st.success(f"Application #{app_id} created. Go to Upload documents next.")

elif page == "Upload documents":
    st.subheader("Upload supporting documents")
    if not applications:
        st.info("Create an application first.")
    else:
        labels = {f"#{x['id']} — {x['institution']} ({x['category']})": x["id"] for x in applications}
        chosen = st.selectbox("Select application", list(labels.keys()))
        app_id = labels[chosen]
        files_in = st.file_uploader(
            "Choose PDF or image files", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True
        )
        if files_in:
            st.caption("Digital PDFs use embedded text when available. Scanned PDFs and images are processed with Tesseract OCR.")
        if st.button("Save uploaded documents", type="primary", disabled=not files_in):
            saved = 0
            for f in files_in:
                data = f.getvalue()
                digest = sha256(data)
                safe_name = re.sub(r"[^A-Za-z0-9.\_-]", "_", f.name)
                stored = UPLOAD_DIR / f"{app_id}_{digest[:10]}_{safe_name}"
                stored.write_bytes(data)
                text = extract_document_text(data, f.name)
                doc_type = classify_doc(f.name)
                with db() as con:
                    con.execute(
                        "INSERT INTO documents(application_id,filename,doc_type,extracted_text,sha256,uploaded_at) VALUES(?,?,?,?,?,?)",
                        (app_id, f.name, doc_type, text, digest, datetime.now().isoformat(timespec="seconds")),
                    )
                audit(app_id, "Document uploaded", f"{f.name} ({doc_type})")
                saved += 1
            st.success(f"Saved {saved} document(s). Go to Validate & review.")
        with db() as con:
            docs = con.execute("SELECT * FROM documents WHERE application_id=? ORDER BY id DESC", (app_id,)).fetchall()
        if docs:
            st.markdown("**Uploaded files**")
            st.dataframe([
                {
                    "Filename": d["filename"],
                    "Detected type": d["doc_type"],
                    "Text extracted": "Yes" if (d["extracted_text"] or "").strip() else "No / manual review",
                    "SHA-256": (d["sha256"] or "")[:16] + "…",
                }
                for d in docs
            ], use_container_width=True, hide_index=True)
            
            st.subheader("Extracted Text Preview")

            for d in docs:
                with st.expander(f"View text: {d['filename']}"):
                    extracted_text = d["extracted_text"] or ""

                    if extracted_text.strip():
                        st.text_area(
                            "Extracted document text",
                            value=extracted_text[:3000],
                            height=200,
                            key=f"ocr_preview_{d['id']}",
                            disabled=True,
                        )
                    else:
                        st.warning(
                            "No text extracted. Check document quality "
                            "or review it manually."
                        )



elif page == "Validate & review":
    st.subheader("Run validation and review results")
    if not applications:
        st.info("Create an application first.")
    else:
        labels = {f"#{x['id']} — {x['institution']}": x["id"] for x in applications}
        chosen = st.selectbox("Select application to validate", list(labels.keys()))
        app_id = labels[chosen]
        with db() as con:
            app = con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
            docs = con.execute("SELECT * FROM documents WHERE application_id=? ORDER BY id", (app_id,)).fetchall()
        st.write(f"**Category:** {app['category']} | **Current status:** {app['status']}")
        if st.button("Run validation checks", type="primary"):
            n = run_validation(app_id)
            st.success(f"Validation finished. {n} finding(s) generated.")
        with db() as con:
            findings = con.execute("SELECT * FROM findings WHERE application_id=? ORDER BY id DESC", (app_id,)).fetchall()
        if findings:
            for f in findings:
                with st.expander(f"{status_badge(f['status'])} — {f['rule_code']}: {f['explanation']}", expanded=f["status"] != "Passed"):
                    st.write("**Explanation:**", f["explanation"])
                    st.write("**Evidence / next step:**", f["evidence"] or "No additional evidence recorded.")
                    st.caption(f"Finding created: {f['created_at']}")
            report = {
                "application": dict(app),
                "documents": [{"filename": d["filename"], "type": d["doc_type"]} for d in docs],
                "findings": [dict(f) for f in findings],
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "notice": "Advisory prototype output; not an AICTE decision.",
            }
            st.download_button(
                "Download validation report (JSON)", json.dumps(report, indent=2),
                file_name=f"smartverify_application_{app_id}_report.json", mime="application/json",
            )
        st.divider()
        st.subheader("Demo issuer verification")
        st.caption("This is simulated only; it does not contact any issuing authority.")
        with st.form("issuer_demo"):
            cert_no = st.text_input("Certificate / reference number", placeholder="Example: DEMO-123")
            source = st.selectbox("Demo issuer source", [
                "Demo Certificate Registry", "Demo Accreditation Registry", "Demo Permission Registry"
            ])
            submitted = st.form_submit_button("Run simulated check")
        if submitted:
            result = "Verified (demo)" if cert_no.strip().upper().startswith("DEMO-") else "Mismatch (demo)"
            detail = (
                "A matching sample record was found in the simulated registry."
                if result == "Verified (demo)"
                else "No matching sample record in the simulated registry. This is not evidence of forgery."
            )
            st.info(f"{status_badge(result)} — {detail}")
            audit(app_id, "Simulated issuer verification", f"Source={source}; reference={cert_no}; result={result}")


elif page == "Student Data Validation":
    from student_validation import validate_student_data

    st.subheader("Student Data Validation")

    try:
        students, findings = validate_student_data()

        # Main summary
        col1, col2, col3 = st.columns(3)

        col1.metric("Student Records", len(students))
        col2.metric("Flagged Issues", len(findings))
        col3.metric(
            "Records with APAAR IDs",
            int(students["apaar_id"].str.strip().ne("").sum())
        )

        # Student records
        st.subheader("Student Records")
        st.dataframe(
            students,
            use_container_width=True,
            hide_index=True
        )

        # Compliance findings
        st.subheader("Compliance Findings")

        if findings.empty:
            st.success("No compliance issues found.")

        else:
            high = int((findings["Severity"] == "High").sum())
            medium = int((findings["Severity"] == "Medium").sum())
            review = int((findings["Severity"] == "Review").sum())

            col1, col2, col3 = st.columns(3)
            col1.metric("High Severity", high)
            col2.metric("Medium Severity", medium)
            col3.metric("Needs Review", review)

            # Severity filter
            severity_options = ["All"] + sorted(
                findings["Severity"].dropna().unique().tolist()
            )

            selected_severity = st.selectbox(
                "Filter by Severity",
                severity_options
            )

            if selected_severity == "All":
                filtered_findings = findings
            else:
                filtered_findings = findings[
                    findings["Severity"] == selected_severity
                ]

            st.dataframe(
                filtered_findings,
                use_container_width=True,
                hide_index=True
            )

            # Download filtered results
            st.download_button(
                label="Download Findings CSV",
                data=filtered_findings.to_csv(
                    index=False
                ).encode("utf-8"),
                file_name="student_compliance_findings.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Student data validation failed: {e}")



elif page == "Audit history":
    st.subheader("Audit history")
    with db() as con:
        logs = con.execute(
            """SELECT a.id application_id, a.institution, l.action, l.details, l.timestamp
               FROM audit_logs l LEFT JOIN applications a ON a.id=l.application_id
               ORDER BY l.id DESC LIMIT 500"""
        ).fetchall()
    if logs:
        st.dataframe([dict(x) for x in logs], use_container_width=True, hide_index=True)
        st.caption("Audit entries are stored in the local prototype database. A production system would need stronger tamper-evident logging and access controls.")
    else:
        st.info("No audit events yet.")

st.sidebar.divider()
st.sidebar.caption("Document Verification System")
