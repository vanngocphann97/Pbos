# Document Intake — Agent #01

Windows desktop document intake agent for Benthanh House workflow.

Flow: 01_INBOX -> OCR/Extract -> Confidence -> auto-complete (>=90) or 03_REVIEW (<90).

Key behaviors:
- Vietnamese + English OCR
- No QR processing
- SHA-256 duplicate detection
- Audit log
- Automatic file naming and routing
- Human review only for exceptions
- Windows one-file EXE build through GitHub Actions

Version: 2.1.0 Agent #01
