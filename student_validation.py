
from pathlib import Path
import pandas as pd
import re

BASE_DIR = Path(__file__).resolve().parent

STUDENTS_FILE = BASE_DIR / "smartverify_demo_students.csv"
INSTITUTIONS_FILE = BASE_DIR / "smartverify_demo_institutions.csv"


def validate_student_data():
    students = pd.read_csv(STUDENTS_FILE, dtype=str).fillna("")
    institutions = pd.read_csv(INSTITUTIONS_FILE, dtype=str).fillna("")

    students["academic_year"] = pd.to_numeric(
        students["academic_year"], errors="coerce"
    )
    institutions["academic_year"] = pd.to_numeric(
        institutions["academic_year"], errors="coerce"
    )
    institutions["approved_intake"] = pd.to_numeric(
        institutions["approved_intake"], errors="coerce"
    )

    findings = []

    # 1. Missing APAAR IDs
    for _, row in students.iterrows():
        if not row["apaar_id"].strip():
            findings.append({
                "Student Record": row["student_record_id"],
                "Institution": row["institution_name"],
                "Issue": "Missing APAAR ID",
                "Evidence": "APAAR ID is empty"
            })

    # 2. Duplicate APAAR IDs
    valid_ids = students["apaar_id"].str.strip()
    duplicates = valid_ids.ne("") & valid_ids.duplicated(keep=False)

    for _, row in students[duplicates].iterrows():
        findings.append({
            "Student Record": row["student_record_id"],
            "Institution": row["institution_name"],
            "Issue": "Duplicate APAAR ID",
            "Evidence": row["apaar_id"]
        })

    # 3. Invalid demo ID format
    for _, row in students.iterrows():
        apaar_id = row["apaar_id"].strip()
        if apaar_id and not re.fullmatch(r"APAR-DEMO-\d{4}", apaar_id):
            findings.append({
                "Student Record": row["student_record_id"],
                "Institution": row["institution_name"],
                "Issue": "Invalid demo ID format",
                "Evidence": apaar_id
            })

    # 4. Unknown institution codes
    known_codes = set(institutions["institution_code"].str.strip())

    for _, row in students.iterrows():
        if row["institution_code"].strip() not in known_codes:
            findings.append({
                "Student Record": row["student_record_id"],
                "Institution": row["institution_name"],
                "Issue": "Unknown institution code",
                "Evidence": row["institution_code"]
            })

    # 5. Invalid admission dates
    parsed_dates = pd.to_datetime(
        students["admission_date"], errors="coerce"
    )

    for index, row in students.iterrows():
        if pd.isna(parsed_dates.iloc[index]):
            findings.append({
                "Student Record": row["student_record_id"],
                "Institution": row["institution_name"],
                "Issue": "Invalid admission date",
                "Evidence": row["admission_date"]
            })

    # 6. Approved intake checks
    valid_students = students[
        students["institution_code"].isin(known_codes)
        & students["academic_year"].notna()
    ]

    counts = valid_students.groupby(
        ["institution_code", "programme", "academic_year"]
    ).size()

    for _, inst in institutions.iterrows():
        key = (
            inst["institution_code"],
            inst["programme"],
            inst["academic_year"]
        )
        count = counts.get(key, 0)
        intake = inst["approved_intake"]

        if pd.notna(intake) and count > intake:
            findings.append({
                "Student Record": "Multiple records",
                "Institution": inst["institution_name"],
                "Issue": "Approved intake exceeded",
                "Evidence": (
                    f"{inst['programme']}: {count} records "
                    f"against intake of {int(intake)}"
                )
            })

    findings_df = pd.DataFrame(
        findings,
        columns=["Student Record", "Institution", "Issue", "Evidence"]
    )

    # Compliance guidance
    compliance_guidance = {
        "Missing APAAR ID": (
            "High",
            "The student record has no APAAR ID.",
            "Verify the student's APAAR ID and update the record."
        ),
        "Duplicate APAAR ID": (
            "High",
            "The same APAAR ID appears in multiple student records.",
            "Review the records and confirm whether they belong to the same student."
        ),
        "Invalid demo ID format": (
            "Medium",
            "The ID does not match the expected demo format.",
            "Check the ID format against the configured demo rule."
        ),
        "Unknown institution code": (
            "High",
            "The institution code was not found in the institution dataset.",
            "Confirm the institution code and update the institution reference data if appropriate."
        ),
        "Invalid admission date": (
            "Medium",
            "The admission date is missing or cannot be parsed.",
            "Verify the date and enter it in a supported format."
        ),
        "Approved intake exceeded": (
            "High",
            "The number of student records exceeds the configured approved intake.",
            "Review the programme's admission count and approved intake."
        )
    }

    findings_df["Severity"] = findings_df["Issue"].map(
        lambda issue: compliance_guidance.get(
            issue,
            ("Review", "Manual review is required.", "Review the flagged record.")
        )[0]
    )

    findings_df["Reason"] = findings_df["Issue"].map(
        lambda issue: compliance_guidance.get(
            issue,
            ("Review", "Manual review is required.", "Review the flagged record.")
        )[1]
    )

    findings_df["Recommended Action"] = findings_df["Issue"].map(
        lambda issue: compliance_guidance.get(
            issue,
            ("Review", "Manual review is required.", "Review the flagged record.")
        )[2]
    )

    return students, findings_df
