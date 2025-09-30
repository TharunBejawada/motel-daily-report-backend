# app/parsers/docx_text.py
import io
from docx import Document

def extract_text_from_docx(data: bytes) -> str:
    try:
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        print("[DOCX Parse Error]", e)
        return ""
