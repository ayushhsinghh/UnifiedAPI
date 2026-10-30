"""Bounded, fixed-source matching for constitutional excerpts. Never fetch model URLs."""
import asyncio
import io
import re
import threading
import time
from datetime import datetime, timezone

SOURCE_URL = 'https://lddashboard.legislative.gov.in/sites/default/files/coi/COI_2024.pdf'
EDITION_DATE = '2024-05-01'
_cache = None
_lock = threading.Lock()


def normalize_text(value):
    return re.sub(r'\s+', ' ', value).strip()


def article_excerpt(document, reference, candidate):
    """Match exact words inside the named Article, allowing only whitespace differences."""
    match = re.fullmatch(r'Article ([1-9][0-9]{0,2}[A-Z]{0,2})', reference)
    if not match or not isinstance(candidate, str) or not 40 <= len(candidate) <= 1200:
        return None
    number = match[1]
    # Contents entries are usually short; search each numbered body occurrence independently.
    for start in re.finditer(r'(?m)^\s*' + re.escape(number) + r'\.\s+', document):
        tail = document[start.end():]
        end = re.search(r'(?m)^\s*[1-9][0-9]{0,2}[A-Z]{0,2}\.\s+', tail)
        if not end:
            continue  # Without a closing boundary, fail closed rather than match another provision.
        body = normalize_text(tail[:end.start()])
        wanted = normalize_text(candidate)
        if wanted and wanted in body:
            return wanted
    return None


def _load_official_text():
    global _cache
    with _lock:
        now = time.monotonic()
        if _cache and now - _cache[0] < (3600 if _cache[1] else 300):
            return _cache[1], _cache[2]
        try:
            import requests
            from pypdf import PdfReader
            with requests.get(SOURCE_URL, stream=True, timeout=(3, 7), allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected source response')
                data = bytearray()
                for chunk in response.iter_content(65536):
                    if time.monotonic() - now > 10:
                        raise TimeoutError('Source download deadline exceeded')
                    data.extend(chunk)
                    if len(data) > 8 * 1024 * 1024:
                        raise ValueError('Source exceeds size limit')
            if not data.startswith(b'%PDF-'):
                raise ValueError('Source is not a PDF')
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 1000:
                raise ValueError('Unsupported source document')
            pages, size = [], 0
            for page in reader.pages:
                if time.monotonic() - now > 10:
                    raise TimeoutError('Source extraction deadline exceeded')
                text = page.extract_text() or ''
                size += len(text)
                if size > 3_000_000:
                    raise ValueError('Source text exceeds limit')
                pages.append(text)
            document = '\n'.join(pages)
            checked_at = datetime.now(timezone.utc).isoformat()
            _cache = (now, document, checked_at)
        except Exception:
            _cache = (now, '', None)
        return _cache[1], _cache[2]


async def enrich_constitution_text(fact, loader=None):
    """Overwrite all model-supplied quotation/verification metadata before persistence."""
    lesson = fact['constitution_lesson']
    bases = lesson['constitutional_basis']
    # Generate fresh objects: no provider-supplied verification fields survive.
    for basis in bases:
        basis.pop('original_text', None)
        basis.pop('text_verification', None)
    lesson['source_context'] = {'edition_date': EDITION_DATE, 'official_url': SOURCE_URL,
                                'source_checked_at': None, 'current_law_verified_at': None}
    document, checked_at = '', None
    if any(basis.get('quote_candidate') for basis in bases):
        try:
            document, checked_at = await asyncio.wait_for(asyncio.to_thread(loader or _load_official_text), timeout=12)
        except Exception:
            pass
    lesson['source_context']['source_checked_at'] = checked_at
    for basis in bases:
        candidate = basis.pop('quote_candidate', '')
        excerpt = article_excerpt(document, basis['reference'], candidate) if document else None
        basis['original_text'] = excerpt or ''
        basis['text_verification'] = {'status': 'matched_official_edition' if excerpt else 'not_verified',
                                     'checked_at': datetime.now(timezone.utc).isoformat() if excerpt else None,
                                     'edition_date': EDITION_DATE, 'source_url': SOURCE_URL}
    fact['constitution_validation'] = {'structure_checked': True, 'legal_review': 'not_performed',
                                        'current_law_verification': 'not_performed'}
    return fact
