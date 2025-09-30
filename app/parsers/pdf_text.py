# app/parsers/pdf_text.py
import io
import os
import pdfplumber
from PyPDF2 import PdfReader
from openai import OpenAI
import base64

# ✅ initialize once globally
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _basic_pdf_text(pdf_bytes: bytes) -> str:
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
    except Exception:
        pass

    if len(text.strip()) < 50:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                text += page.extract_text() or ""
        except Exception:
            pass
    return text.strip()

def _gpt_vision_extract(pdf_bytes: bytes) -> str:
    """
    OCR scanned PDFs using GPT-4.1-mini.
    ✅ Fully compatible with openai==1.109.x
    ✅ Properly sets filename and MIME type
    ✅ Handles scanned tables too
    """
    try:
        # ✅ Upload PDF with filename and correct MIME type
        uploaded_file = client.files.create(
            file=("daily_report.pdf", io.BytesIO(pdf_bytes), "application/pdf"),
            purpose="assistants"
        )

        print(f"📤 Uploaded PDF to OpenAI, file_id={uploaded_file.id}")

        # ✅ Use the uploaded file in chat completion
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an OCR assistant. Extract ALL visible text "
                        "from the uploaded motel daily report PDF. Preserve table structures "
                        "as readable text. Do NOT summarize — return full raw text."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract text from this scanned PDF:"},
                        {"type": "file", "file": {"file_id": uploaded_file.id}}
                    ]
                }
            ]
        )

        text = response.choices[0].message.content.strip()
        print("📄 DEBUG: GPT OCR text preview:", text[:500], "..." if len(text) > 500 else "")
        return text

    except Exception as e:
        print(f"[GPT OCR Fallback Error] {e}")
        return ""

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    text = _basic_pdf_text(pdf_bytes)
    if len(text) < 100:
        print("⚠️ PDF appears to be scanned. Falling back to GPT OCR...")
        text = _gpt_vision_extract(pdf_bytes)
    return text
