"""Disposable pypdf worker. JSON stdout only, bounded CPU/address space/output."""
import json
import resource
import sys

MAX_TEXT = 2_000_000


def main():
    resource.setrlimit(resource.RLIMIT_CPU,(55,55))
    # Darwin rejects RLIMIT_AS on supported Python builds; the parent
    # enforces an RSS ceiling there instead of silently claiming this limit.
    if sys.platform != 'darwin':
        resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
    from pypdf import PdfReader
    reader = PdfReader(sys.argv[1], strict=False)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDFs are not supported.')
    count = len(reader.pages)
    if not 1 <= count <= 200:
        raise ValueError('PDFs must contain at most 200 pages.')
    pages=[]; size=0; partial=[]
    for number,page in enumerate(reader.pages,1):
        try:
            value=page.extract_text() or ''
        except Exception:
            value=''
        size+=len(value)
        if size>MAX_TEXT:
            raise ValueError('Extracted PDF text exceeds the safe limit.')
        if not value.strip():
            partial.append(number)
        pages.append({'page':number,'text':value})
    if not any(p['text'].strip() for p in pages):
        raise ValueError('No readable text. Image-only PDFs need OCR and are not supported.')
    print(json.dumps({'pages':pages,'warning':'Unreadable or textless pages: '+', '.join(map(str,partial))+'.' if partial else ''},ensure_ascii=False))


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error':str(exc)[:300]}))
        sys.exit(1)
