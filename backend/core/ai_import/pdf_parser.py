from __future__ import annotations

import pdfplumber


def extract_text_from_pdf(file_path: str) -> str:
    """Извлекает объединённый текст из всех страниц PDF."""
    parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
    return "\n\n".join(parts)
