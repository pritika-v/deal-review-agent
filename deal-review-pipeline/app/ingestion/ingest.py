from __future__ import annotations
import io, re, hashlib, logging
from pathlib import Path
import fitz
import numpy as np
from PIL import Image
from app.models.schemas import DocumentChunk

log = logging.getLogger(__name__)

class IngestionError(RuntimeError): pass

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception:
    RapidOCR = None


def _ocr_page(page, engine) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    result, _ = engine(np.array(image))
    if not result: return ''
    lines = []
    for item in result:
        if len(item) >= 3:
            text, score = str(item[1]), float(item[2])
            if score >= 0.35: lines.append(text)
    return '\n'.join(lines)

def ingest_pdf(path: str, document_id: str | None = None) -> tuple[str, list[dict], list[DocumentChunk]]:
    p = Path(path)
    if not p.exists(): raise IngestionError(f'Document not found: {p}')
    document_id = document_id or hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    doc = fitz.open(str(p))
    pages=[]
    ocr_engine = RapidOCR() if RapidOCR else None
    for i, page in enumerate(doc, start=1):
        native = page.get_text('text').strip()
        text = native
        # OCR is activated for image/scanned pages or very sparse native extraction.
        if ocr_engine and len(native) < 120:
            try: text = _ocr_page(page, ocr_engine).strip() or native
            except Exception as exc: log.warning('OCR failed on page %s: %s', i, exc)
        # Keep a page-level record even when text is sparse so missing evidence remains explicit.
        sections = re.findall(r'(?im)^(?:[A-Z][A-Z &/,-]{3,}|TERMS AND CONDITIONS|PAYMENT TERMS|FURTHER TERMS).*$', text)
        clauses = re.findall(r'(?m)^\s*(\d+\.)\s+(.{3,180})', text)
        pages.append({'page':i,'text':text,'sections':sections,'clauses':[x[1] for x in clauses],
                      'metadata':{'width':page.rect.width,'height':page.rect.height,'ocr_used':len(native)<120 and bool(ocr_engine)}})
    chunks=[]
    chunk_size=900; overlap=120
    for pg in pages:
        words=pg['text'].split()
        section=pg['sections'][0] if pg['sections'] else None
        clause=pg['clauses'][0] if pg['clauses'] else None
        if not words:
            continue
        start=0; idx=0
        while start < len(words):
            end=min(len(words), start+chunk_size)
            txt=' '.join(words[start:end])
            chunks.append(DocumentChunk(document_id=document_id,chunk_id=f'{document_id}-p{pg["page"]}-c{idx}',page=pg['page'],text=txt,section=section,clause=clause))
            idx+=1
            if end==len(words): break
            start=end-overlap
    if not chunks: raise IngestionError('No text could be extracted from the PDF, including OCR fallback.')
    return document_id, pages, chunks
