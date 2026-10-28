# AICTE SmartVerify — 2-day prototype

A beginner-friendly Streamlit web prototype for AICTE problem statement 26261.

## Features
- Application creation and dashboard
- PDF/image uploads
- Text extraction from digital PDFs
- Filename-based document type suggestion
- Configurable demo checklist
- Missing document, expiry-date, cross-document code mismatch and duplicate-file flags
- Simulated issuer verification (clearly labelled)
- Findings with evidence and next steps
- JSON validation report download
- Local SQLite database and audit history

## Requirements
- Python 3.10+ recommended
- Internet connection for the initial package installation

## Run on Windows
Open Command Prompt in this folder:

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If `py` is not recognized, use `python` instead:
```bat
python -m venv .venv
.venv\Scripts\activate
```

Streamlit prints a local URL, usually http://localhost:8501. Open it in your browser.

## Demo scenario
1. Create an application named `Sunrise Institute of Technology`, code `DEMO-102`.
2. Upload digital PDF files with filenames such as `affidavit.pdf`, `noc.pdf`, `previous_approval.pdf`.
3. For expiry detection, include text in a PDF such as `Valid until: 2024-12-31`.
4. To demonstrate a cross-document mismatch, put `Institution Code: DEMO-102` in one PDF and `Institution Code: DEMO-999` in another.
5. Run validation and review the findings.
6. Try the demo issuer check: references beginning `DEMO-` show a simulated match; other references show a simulated non-match.

## Important limitations
- This is a prototype, not an official AICTE product and not connected to AICTE or government databases.
- The checklist is illustrative and must be replaced with verified, category-specific rules before real use.
- PDF text extraction works best on digital PDFs. Scanned PDFs and images are flagged for manual review; OCR is not bundled in this minimal version.
- A demo issuer match is not real authentication.
- Automated flags are advisory. Authorized officials retain regulatory review and final decisions.
- Uploaded files and the SQLite database are stored locally in this folder. Do not use real personal or confidential records in the demo.

## Reset demo data
Stop Streamlit, then delete `smartverify.db` and the files inside `uploads/`. The app recreates the database at next start.
