"""Resumable source extraction shared by chat preprocessing and attachment tools."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, List

from . import attachments
from .vault import IMAGE_EXT

log = logging.getLogger(__name__)


async def analyse_attachments(chat_id: str, items: List[dict], frage: str,
                     vision, runner) -> AsyncIterator[dict]:
    """Persist every source/page before continuing; resume completed units."""
    analysis = await asyncio.to_thread(attachments.load_analysis, chat_id)
    auftrag = (
        "Erfasse ALLE lesbaren Texte, Kennungen, Zahlen, Beschriftungen und Tabellen "
        "dieser Seite vollständig. Beschreibe außerdem Diagramme, Bilder und ihre "
        "erkennbaren Beziehungen. Trenne wörtliche Abschrift von Bildbeschreibung. "
        "Kennzeichne Unlesbares und Unsicheres; erfinde nichts. Diese Arbeitsnotizen "
        "werden für spätere Aufgaben gespeichert, kürze sie nicht auf die aktuelle Frage."
    )
    for nummer, item in enumerate(items, start=1):
        name = item["name"]
        record = analysis["progress"].get(name, {})
        progress = {"name": name, "nummer": nummer, "gesamt": len(items), "kind": item["kind"]}
        if record.get("complete"):
            yield {"fortschritt": {**progress, "status": "cached",
                                  "text": analysis["items"].get(name, "")}}
            continue
        yield {"fortschritt": {**progress, "status": "reading"}}
        parts = record.get("parts", {})
        active_part = "image"
        try:
            path = await asyncio.to_thread(attachments.resolve, chat_id, name)
            if path.suffix.lower() == ".pdf":
                pages = await asyncio.to_thread(attachments.pdf_text_pages, path)
                if not pages:
                    raise ValueError("PDF enthält keine lesbaren Seiten.")
                for index, text in enumerate(pages):
                    key = f"page:{index + 1}"
                    if key + ":text" not in parts:
                        await asyncio.to_thread(attachments.checkpoint, chat_id, name,
                                                key + ":text", f"--- Seite {index + 1}: Text ---\n{text}")
                    if vision is not None and key + ":vision" not in parts:
                        yield {"fortschritt": {**progress, "status": "reading",
                                              "seite": index + 1, "seiten": len(pages)}}
                        image = await asyncio.to_thread(attachments.pdf_page_image, path, index)
                        active_part = key + ":vision"
                        description = await vision(auftrag, image)
                        await asyncio.to_thread(attachments.checkpoint, chat_id, name,
                                                key + ":vision", f"--- Seite {index + 1}: Bildauswertung ---\n{description}")
                    yield {"fortschritt": {**progress, "status": "saved",
                                          "seite": index + 1, "seiten": len(pages)}}
                if vision is None:
                    raise ValueError("PDF-Text gespeichert; Bilder und Scans benötigen ein Modell mit Bildunterstützung.")
            elif path.suffix.lower() in IMAGE_EXT:
                if vision is None:
                    raise ValueError("Das gewählte Modell unterstützt keine Bildauswertung.")
                image = await asyncio.to_thread(attachments.image_base64, path)
                text = await vision(auftrag, image)
                await asyncio.to_thread(attachments.checkpoint, chat_id, name, "image", text)
            else:
                result = await asyncio.to_thread(attachments.extract_text, path, True)
                if result.get("fehler"):
                    raise ValueError(result["fehler"])
                await asyncio.to_thread(attachments.checkpoint, chat_id, name, "text",
                                        result.get("text") or "(kein lesbarer Text)")
                if path.suffix.lower() == ".docx":
                    images = await asyncio.to_thread(attachments.docx_images, path)
                    if images and vision is None:
                        raise ValueError("Word-Text gespeichert; eingebettete Bilder benötigen Bildunterstützung.")
                    for image_name, image_data in images:
                        active_part = image_name
                        if active_part in parts:
                            continue
                        image = await asyncio.to_thread(attachments.image_bytes_base64, image_data)
                        description = await vision(auftrag, image)
                        await asyncio.to_thread(attachments.checkpoint, chat_id, name,
                                                active_part, f"--- {image_name} ---\n{description}")
            await asyncio.to_thread(attachments.checkpoint, chat_id, name, complete=True)
        except Exception as exc:
            log.warning("Anhang %s unvollständig: %s", name, exc)
            if isinstance(exc, attachments.AnalysisIncomplete) and exc.partial:
                await asyncio.to_thread(attachments.checkpoint, chat_id, name,
                                        active_part + ":partial", exc.partial)
            await asyncio.to_thread(attachments.checkpoint, chat_id, name, error=str(exc))
        result = await asyncio.to_thread(attachments.load_analysis, chat_id)
        status = result["progress"].get(name, {})
        yield {"fortschritt": {**progress, "status": "saved" if status.get("complete") else "partial",
                              "text": result["items"].get(name, ""), "error": status.get("error", "")}}
    result = await asyncio.to_thread(attachments.load_analysis, chat_id)
    yield {"fertig": True, "cache": result["items"], "progress": result["progress"]}

