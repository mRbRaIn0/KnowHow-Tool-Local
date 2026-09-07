"""Isolated optional worker. Inputs are local paths; network access is denied."""
import json
import socket
import sys
from pathlib import Path


def deny_network(*args, **kwargs):
    raise RuntimeError("Netzwerkzugriff ist in der Dokumentanalyse deaktiviert.")


socket.create_connection = deny_network
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network

from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions

path, models = Path(sys.argv[1]), Path(sys.argv[2])
if not path.is_absolute() or not path.is_file() or not models.is_dir():
    raise RuntimeError("Lokale Datei und vorinstallierte Modelle erforderlich.")
options = PdfPipelineOptions(artifacts_path=models, enable_remote_services=False)
options.ocr_options = EasyOcrOptions(lang=["de", "en"], download_enabled=False)
converter = DocumentConverter(format_options={
    InputFormat.PDF: PdfFormatOption(pipeline_options=options),
    InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
})
result = converter.convert(path, max_num_pages=300, max_file_size=200 * 1024 * 1024)
chunks = []
for element, _ in result.document.iterate_items():
    text = getattr(element, "text", "") or ""
    if not text and hasattr(element, "export_to_markdown"):
        text = element.export_to_markdown(doc=result.document)
    provenance = getattr(element, "prov", [])
    page = provenance[0].page_no if provenance else 0
    for start in range(0, len(text), 1200):
        chunks.append({"page": page, "content": text[start:start + 1400], "embedding": []})
print(json.dumps(chunks, ensure_ascii=False))
