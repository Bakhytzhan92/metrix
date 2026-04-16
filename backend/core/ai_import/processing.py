from __future__ import annotations

import logging
import os

from django.apps import apps

logger = logging.getLogger(__name__)


def process_document(document_id: int) -> None:
    """
    Извлекает текст из PDF, вызывает ИИ, обновляет UploadedDocument.
    Предполагается вызов из request/transaction; ошибки пишутся в status=error.
    """
    UploadedDocument = apps.get_model("core", "UploadedDocument")
    doc = UploadedDocument.objects.get(pk=document_id)
    doc.status = UploadedDocument.STATUS_PROCESSING
    doc.error_message = ""
    doc.save(update_fields=["status", "error_message"])

    path = doc.file.path
    try:
        from .pdf_parser import extract_text_from_pdf
        from .ai_service import generate_project_plan

        if not os.path.isfile(path):
            raise FileNotFoundError(f"Файл не найден: {path}")

        text = extract_text_from_pdf(path)
        doc.parsed_text = text[:500_000] if text else ""
        doc.save(update_fields=["parsed_text"])

        if not (doc.parsed_text or "").strip():
            raise ValueError(
                "Не удалось извлечь текст из PDF (пустой документ или скан без OCR)."
            )

        plan = generate_project_plan(doc.parsed_text, project_type=doc.project_type)
        doc.ai_result = plan
        doc.status = UploadedDocument.STATUS_DONE
        doc.save(update_fields=["ai_result", "status"])
    except Exception as e:
        logger.exception("process_document failed for id=%s", document_id)
        doc.refresh_from_db()
        doc.status = UploadedDocument.STATUS_ERROR
        doc.error_message = str(e)[:2000]
        doc.save(update_fields=["status", "error_message"])
