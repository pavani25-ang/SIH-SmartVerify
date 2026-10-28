
import re


def extract_student_fields(text):
    """Extract common student details from OCR text."""

    patterns = {
        "student_name": r"(?im)^\s*Student\s*Name\s*[:\-]\s*(.+)$",
        "apaar_id": r"(?im)^\s*APAAR\s*ID\s*[:\-]\s*([A-Z0-9\-]+)",
        "institution_code": (
            r"(?im)^\s*Institution\s*Code\s*[:\-]\s*([A-Z0-9\-]+)"
        ),
        "admission_date": (
            r"(?im)^\s*Admission\s*Date\s*[:\-]\s*(.+)$"
        ),
    }

    result = {}

    for field, pattern in patterns.items():
        match = re.search(pattern, text or "")
        result[field] = match.group(1).strip() if match else ""

    return result
