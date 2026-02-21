"""
Core citation search logic using Semantic Scholar API.
"""

import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_API_KEY = os.environ.get('SEMANTIC_SCHOLAR_API_KEY', '')
_REQUEST_HEADERS = {'x-api-key': _API_KEY} if _API_KEY else {}

# Simple in-process LRU-style cache (max 256 entries)
_SEARCH_CACHE: dict = {}
_CACHE_MAX = 256

# Patterns that signal a claim needing citation
CITATION_INDICATORS = [
    # Existing patterns
    r'\bstudies (show|suggest|indicate|demonstrate|have shown)\b',
    r'\bresearch (shows|suggests|indicates|demonstrates|has shown)\b',
    r'\bevidence (suggests|indicates|shows|demonstrates)\b',
    r'\bit (has been|is) (shown|demonstrated|found|reported|established)\b',
    r'\baccording to\b',
    r'\bhas been (proven|demonstrated|established|shown)\b',
    r'\bstatistics (show|indicate|suggest)\b',
    r'\bdata (shows|indicates|suggests|demonstrate)\b',
    r'\bexperts (argue|suggest|believe|claim|agree)\b',
    r'\bis (widely|generally|commonly) (accepted|known|believed|recognized)\b',
    r'\bhas a significant (effect|impact|influence)\b',
    r'\b(increases|decreases|improves|reduces|enhances|affects)\b',
    r'\b\d+\s*%',
    r'\bcompared to\b',
    r'\bsignificant(ly)?\b',
    # Causation
    r'\b(causes|caused by|leads? to|results? in|due to|attributed to)\b',
    # Correlation / association
    r'\b(correlated|associated|linked|related) with\b',
    r'\b(positive|negative|strong|weak) (correlation|association|relationship)\b',
    # Comparative quantitative claims
    r'\b(higher|lower|greater|fewer|more|less) than\b',
    r'\b\d+\s*(times|fold)\b',
    # Population / prevalence claims
    r'\b(most|many|majority of|nearly all|approximately|about)\b.*\b(people|patients|individuals|participants|adults|children|women|men)\b',
    r'\b(prevalence|incidence|proportion|rate) of\b',
    # Prior literature
    r'\b(previous|prior|earlier|recent|past) (studies|research|work|literature|findings)\b',
    r'\b(meta-analysis|systematic review|randomized|clinical trial|cohort study|longitudinal)\b',
    # Risk / benefit
    r'\b(risk|benefit|efficacy|effectiveness|safety) of\b',
    r'\b(reduces?|increases?) (the )?(risk|likelihood|chance|probability)\b',
    # Definition / classification claims
    r'\bis (defined|classified|characterized) as\b',
    r'\brefers? to\b',
    # Temporal trends
    r'\bover the (past|last) (decade|century|years?|decades?)\b',
    r'\b(growing|increasing|declining|rising) (evidence|trend|number|rate|concern)\b',
    # Numeric facts
    r'\b\d{1,3}(,\d{3})+ (people|cases|deaths|patients)\b',
    r'\bapproximately \d+\b',
]

CITATION_REASONS = [
    'Studies claim', 'Research claims', 'Evidence cited',
    'Passive claim', 'Attribution needed', 'Established claim',
    'Statistical claim', 'Data claim', 'Expert opinion',
    'Accepted belief', 'Impact claim', 'Effect claim',
    'Percentage figure', 'Comparison claim', 'Significant claim',
    'Causation claim', 'Causation claim',
    'Correlation claim', 'Correlation claim',
    'Comparative claim', 'Quantitative claim',
    'Population claim', 'Prevalence claim',
    'Prior literature', 'Study type',
    'Risk/benefit claim', 'Risk claim',
    'Definition claim', 'Reference needed',
    'Temporal trend', 'Growing evidence',
    'Numeric fact', 'Approximate figure',
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CITATION_INDICATORS]
COMPILED_REASONS = list(zip(COMPILED_PATTERNS, CITATION_REASONS))


# Common title/academic abbreviations that should not trigger sentence splits
_DOI_CACHE: dict[str, bool] = {}


def validate_doi(doi: str) -> bool:
    """Return True if the DOI resolves (HEAD request to doi.org)."""
    if not doi:
        return False
    if doi in _DOI_CACHE:
        return _DOI_CACHE[doi]
    try:
        r = requests.head(f"https://doi.org/{doi}", timeout=4, allow_redirects=True)
        result = r.status_code < 400
    except Exception:
        result = False
    if len(_DOI_CACHE) < 1024:
        _DOI_CACHE[doi] = result
    return result


_ABBREV = re.compile(
    r'\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr|vs|etc|al|Fig|et|cf|vol|no|pp|ed|eds|rev|dept|univ|govt|corp|inc|ltd|approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.',
    re.IGNORECASE,
)
_INITIALS = re.compile(r'\b[A-Z]\.')  # single-letter initials


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, avoiding splits after abbreviations and initials."""
    # Temporarily mask abbreviations and initials with a placeholder
    MASK = '\x00'
    masked = _ABBREV.sub(lambda m: m.group(0).replace('.', MASK), text)
    masked = _INITIALS.sub(lambda m: m.group(0).replace('.', MASK), masked)

    # Split on sentence-ending punctuation followed by whitespace + capital/digit
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9\"\'])', masked)

    # Restore masked dots and clean up
    return [p.replace(MASK, '.').strip() for p in parts if len(p.strip()) > 20]


def needs_citation(sentence: str) -> bool:
    """Return True if the sentence likely needs a citation."""
    return get_citation_reason(sentence) is not None


def get_citation_reason(sentence: str) -> Optional[str]:
    """Return a human-readable reason why the sentence needs a citation, or None."""
    if re.search(r'\[\d+\]|\(\w[\w\s]*,?\s*\d{4}\)|\^\d+|ibid\.|op\.\s*cit\.', sentence, re.IGNORECASE):
        return None
    for pattern, reason in COMPILED_REASONS:
        if pattern.search(sentence):
            return reason
    return None


_STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'can', 'it', 'its',
    'this', 'that', 'these', 'those', 'not', 'also', 'which', 'who',
    'studies', 'research', 'show', 'shows', 'shown', 'suggest', 'suggests',
    'evidence', 'data', 'indicates', 'indicate', 'demonstrate', 'demonstrates',
    'according', 'generally', 'commonly', 'widely', 'significant', 'significantly',
    'however', 'therefore', 'furthermore', 'moreover', 'although', 'because',
    'such', 'their', 'they', 'them', 'there', 'been', 'both', 'each',
    'than', 'then', 'when', 'where', 'while', 'thus', 'since', 'after',
}


def build_query(sentence: str) -> str:
    """Extract key terms from sentence for search query.

    Strategy:
    1. Extract capitalized multi-word noun phrases (prioritised as domain concepts).
    2. Fall back to individual content words sorted by length (longer = more specific).
    3. Deduplicate, limit to 8 tokens.
    """
    seen: set[str] = set()
    tokens: list[str] = []

    # Step 1: capitalized bigrams/trigrams (e.g. "Machine Learning", "Climate Change")
    cap_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', sentence)
    for phrase in cap_phrases:
        key = phrase.lower()
        if key not in seen and not all(w in _STOP_WORDS for w in key.split()):
            seen.add(key)
            tokens.append(phrase)

    # Step 2: individual content words, longest first (more specific terms first)
    words = re.findall(r'\b[a-zA-Z]{4,}\b', sentence)
    content = [w for w in words if w.lower() not in _STOP_WORDS and w.lower() not in seen]
    # Deduplicate preserving order, sort longer words first within tie-breaks
    ordered: list[str] = []
    for w in sorted(set(w.lower() for w in content), key=lambda x: -len(x)):
        if w not in seen:
            seen.add(w)
            ordered.append(w)
    tokens.extend(ordered)

    return ' '.join(tokens[:8])


def _get_author_parts(authors: list, style: str) -> str:
    """Helper: format author list for different styles."""
    if not authors:
        return 'Unknown Author'

    def name_parts(a):
        name = a.get('name', '')
        parts = name.split()
        return parts, name

    if style == 'apa':
        def fmt_one(a):
            parts, name = name_parts(a)
            if not parts:
                return name
            last = parts[-1]
            initials = ' '.join(p[0] + '.' for p in parts[:-1] if p)
            return f"{last}, {initials}".strip(', ')
        authors_f = [fmt_one(a) for a in authors]
        if len(authors_f) == 1:
            return authors_f[0]
        elif len(authors_f) <= 6:
            return ', '.join(authors_f[:-1]) + ', & ' + authors_f[-1]
        else:
            return authors_f[0] + ', et al.'

    elif style == 'mla':
        parts, name = name_parts(authors[0])
        first = f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) >= 2 else name
        return first if len(authors) == 1 else first + ', et al.'

    elif style == 'chicago':
        def fmt_one(a, i):
            parts, name = name_parts(a)
            if not parts:
                return name
            if i == 0:
                return f"{parts[-1]}, {' '.join(parts[:-1])}"
            return ' '.join(parts)
        if len(authors) == 1:
            return fmt_one(authors[0], 0)
        elif len(authors) <= 3:
            fmts = [fmt_one(a, i) for i, a in enumerate(authors)]
            return ', and '.join([', '.join(fmts[:-1]), fmts[-1]])
        else:
            return fmt_one(authors[0], 0) + ', et al.'

    elif style == 'ieee':
        def fmt_one(a):
            parts, name = name_parts(a)
            if not parts:
                return name
            initials = '. '.join(p[0] for p in parts[:-1] if p) + '.' if parts[:-1] else ''
            return f"{initials} {parts[-1]}".strip()
        fmts = [fmt_one(a) for a in authors[:3]]
        result = ', '.join(fmts)
        return result + (' et al.' if len(authors) > 3 else '')

    elif style == 'harvard':
        def fmt_one(a):
            parts, name = name_parts(a)
            if not parts:
                return name
            initials = ''.join(p[0] + '.' for p in parts[:-1] if p)
            return f"{parts[-1]}, {initials}".strip(', ')
        fmts = [fmt_one(a) for a in authors]
        if len(fmts) == 1:
            return fmts[0]
        elif len(fmts) <= 3:
            return ', '.join(fmts)
        else:
            return fmts[0] + ' et al.'

    elif style == 'vancouver':
        def fmt_one(a):
            parts, name = name_parts(a)
            if not parts:
                return name
            initials = ''.join(p[0] for p in parts[:-1] if p)
            return f"{parts[-1]} {initials}".strip()
        fmts = [fmt_one(a) for a in authors[:6]]
        result = ', '.join(fmts)
        return result + (', et al.' if len(authors) > 6 else '')

    return 'Unknown Author'


def format_apa(paper: dict) -> str:
    """Format as APA citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    author_str = _get_author_parts(authors, 'apa')
    venue_str = f" *{venue}*." if venue else '.'
    return f"{author_str} ({year}). {title}{venue_str}"


def format_mla(paper: dict) -> str:
    """Format as MLA citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    author_str = _get_author_parts(authors, 'mla')
    venue_str = f" *{venue}*," if venue else ','
    return f'{author_str}. "{title}."{venue_str} {year}.'


def format_chicago(paper: dict) -> str:
    """Format as Chicago author-date citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    author_str = _get_author_parts(authors, 'chicago')
    venue_str = f" *{venue}*." if venue else '.'
    return f'{author_str}. "{title}."{venue_str} {year}.'


def format_ieee(paper: dict) -> str:
    """Format as IEEE citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    author_str = _get_author_parts(authors, 'ieee')
    venue_str = f", *{venue}*" if venue else ''
    return f'{author_str}, "{title}"{venue_str}, {year}.'


def format_harvard(paper: dict) -> str:
    """Format as Harvard citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    author_str = _get_author_parts(authors, 'harvard')
    venue_str = f", *{venue}*" if venue else ''
    return f"{author_str} ({year}) '{title}'{venue_str}."


def format_vancouver(paper: dict) -> str:
    """Format as Vancouver citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    author_str = _get_author_parts(authors, 'vancouver')
    venue_str = f". {venue}" if venue else ''
    return f"{author_str}. {title}{venue_str}. {year}."


def format_bibtex(paper: dict) -> str:
    """Format as BibTeX entry."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    ext_ids = paper.get('externalIds') or {}
    doi = ext_ids.get('DOI', '')

    if authors:
        parts = authors[0].get('name', '').split()
        key_author = parts[-1].lower() if parts else 'unknown'
    else:
        key_author = 'unknown'
    key = f"{key_author}{year}"

    author_names = ' and '.join(a.get('name', '') for a in authors) or 'Unknown Author'
    lines = [
        f"@article{{{key},",
        f"  author  = {{{author_names}}},",
        f"  title   = {{{title}}},",
        f"  year    = {{{year}}},",
    ]
    if venue:
        lines.append(f"  journal = {{{venue}}},")
    if doi:
        lines.append(f"  doi     = {{{doi}}},")
    lines.append("}")
    return '\n'.join(lines)


def format_ris(paper: dict) -> str:
    """Format as RIS entry (compatible with Zotero, Mendeley, EndNote)."""
    authors = paper.get('authors', [])
    year = paper.get('year', '')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')
    ext_ids = paper.get('externalIds') or {}
    doi = ext_ids.get('DOI', '')
    oa_pdf = paper.get('openAccessPdf') or {}
    url = oa_pdf.get('url', '') or paper.get('url', '')

    lines = ['TY  - JOUR']
    for a in authors:
        name = a.get('name', '')
        parts = name.split()
        if len(parts) >= 2:
            lines.append(f"AU  - {parts[-1]}, {' '.join(parts[:-1])}")
        elif name:
            lines.append(f"AU  - {name}")
    lines.append(f"TI  - {title}")
    if venue:
        lines.append(f"JO  - {venue}")
    if year:
        lines.append(f"PY  - {year}")
    if doi:
        lines.append(f"DO  - {doi}")
    if url:
        lines.append(f"UR  - {url}")
    lines.append('ER  - ')
    return '\n'.join(lines)


def search_papers(
    query: str,
    year_range: Optional[tuple[int, int]] = None,
    sources: Optional[list[str]] = None,
    limit: int = 5,
    open_access_only: bool = False,
    fields_of_study: Optional[list[str]] = None,
    min_citation_count: int = 0,
    sort_by: str = 'citations',
) -> list[dict]:
    """Search Semantic Scholar for papers matching query."""
    cache_key = (query, year_range, tuple(sources or []), limit, open_access_only, tuple(fields_of_study or []), min_citation_count, sort_by)
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key]

    params = {
        'query': query,
        'limit': limit,
        'fields': 'title,authors,year,venue,externalIds,abstract,url,openAccessPdf,citationCount',
    }
    if year_range:
        params['year'] = f"{year_range[0]}-{year_range[1]}"
    if fields_of_study:
        params['fieldsOfStudy'] = ','.join(fields_of_study)

    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(SEMANTIC_SCHOLAR_API, params=params, headers=_REQUEST_HEADERS, timeout=10)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2 ** attempt)
    else:
        return []

    try:
        data = resp.json()
        papers = data.get('data', [])

        # Filter open access
        if open_access_only:
            papers = [p for p in papers if p.get('openAccessPdf')]

        # Filter by source/venue if specified
        if sources:
            src_lower = [s.lower() for s in sources]
            papers = [
                p for p in papers
                if any(s in (p.get('venue') or '').lower() for s in src_lower)
            ] or papers  # fall back to all if none match

        # Sort by citation count descending, or keep API relevance order
        if sort_by == 'citations':
            papers.sort(key=lambda p: p.get('citationCount') or 0, reverse=True)

        # Apply minimum citation threshold; fall back to all if none qualify
        if min_citation_count > 0:
            filtered = [p for p in papers if (p.get('citationCount') or 0) >= min_citation_count]
            if filtered:
                papers = filtered

        # Store in cache; evict oldest entry when full
        if len(_SEARCH_CACHE) >= _CACHE_MAX:
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
        _SEARCH_CACHE[cache_key] = papers
        return papers
    except Exception:
        return []


def find_citations_for_text(
    text: str,
    citation_format: str = 'apa',
    year_range: Optional[tuple[int, int]] = None,
    sources: Optional[list[str]] = None,
    results_per_sentence: int = 3,
    open_access_only: bool = False,
    fields_of_study: Optional[list[str]] = None,
    min_citation_count: int = 0,
    sort_by: str = 'citations',
) -> list[dict]:
    """
    Analyze text, detect sentences needing citations, and return
    citation suggestions for each.

    Returns a list of dicts:
      {
        'sentence': str,
        'query': str,
        'citations': [{'formatted': str, 'title': str, 'year': int, 'url': str, 'abstract': str}]
      }
    """
    FORMAT_MAP = {
        'mla': format_mla,
        'chicago': format_chicago,
        'ieee': format_ieee,
        'harvard': format_harvard,
        'vancouver': format_vancouver,
        'bibtex': format_bibtex,
    }
    fmt_fn = FORMAT_MAP.get(citation_format, format_apa)
    fetch_limit = results_per_sentence * 3 if open_access_only else results_per_sentence

    # Collect candidate (sentence, query, reason) triples preserving order
    candidates = []
    for sentence in split_sentences(text):
        reason = get_citation_reason(sentence)
        if reason is None:
            continue
        query = build_query(sentence)
        if query:
            candidates.append((sentence, query, reason))

    if not candidates:
        return []

    def _fetch_and_build(item):
        sentence, query, reason = item
        papers = search_papers(
            query,
            year_range=year_range,
            sources=sources,
            limit=fetch_limit,
            open_access_only=open_access_only,
            fields_of_study=fields_of_study,
            min_citation_count=min_citation_count,
            sort_by=sort_by,
        )
        return sentence, query, reason, papers[:results_per_sentence]

    # Fire all queries in parallel (up to 8 workers)
    ordered: dict[int, tuple] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
        future_to_idx = {pool.submit(_fetch_and_build, c): i for i, c in enumerate(candidates)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                ordered[idx] = future.result()
            except Exception:
                pass

    def _build_citations(papers):
        citations = []
        for paper in papers:
            formatted = fmt_fn(paper)
            ext_ids = paper.get('externalIds') or {}
            doi = ext_ids.get('DOI', '')
            url = paper.get('url', '')
            if doi:
                doi_url = f"https://doi.org/{doi}"
                doi_valid = validate_doi(doi)
                if not url:
                    url = doi_url if doi_valid else ''
            else:
                doi_valid = None
            oa_pdf = paper.get('openAccessPdf') or {}
            pdf_url = oa_pdf.get('url', '')
            citations.append({
                'formatted': formatted,
                'bibtex': format_bibtex(paper),
                'ris': format_ris(paper),
                'title': paper.get('title', ''),
                'year': paper.get('year'),
                'venue': paper.get('venue', ''),
                'doi': doi,
                'doi_valid': doi_valid,
                'url': url,
                'pdf_url': pdf_url,
                'citation_count': paper.get('citationCount'),
                'abstract': paper.get('abstract') or '',
            })
        return citations

    results = []
    for idx in sorted(ordered):
        sentence, query, reason, papers = ordered[idx]
        citations = _build_citations(papers)
        if citations:
            results.append({'sentence': sentence, 'query': query, 'reason': reason, 'citations': citations})

    return results


def stream_citations_for_text(
    text: str,
    citation_format: str = 'apa',
    year_range: Optional[tuple[int, int]] = None,
    sources: Optional[list[str]] = None,
    results_per_sentence: int = 3,
    open_access_only: bool = False,
    fields_of_study: Optional[list[str]] = None,
    min_citation_count: int = 0,
    sort_by: str = 'citations',
):
    """Like find_citations_for_text but yields (index, result) as each sentence completes."""
    FORMAT_MAP = {
        'mla': format_mla, 'chicago': format_chicago, 'ieee': format_ieee,
        'harvard': format_harvard, 'vancouver': format_vancouver, 'bibtex': format_bibtex,
    }
    fmt_fn = FORMAT_MAP.get(citation_format, format_apa)
    fetch_limit = results_per_sentence * 3 if open_access_only else results_per_sentence

    candidates = []
    for sentence in split_sentences(text):
        reason = get_citation_reason(sentence)
        if reason is None:
            continue
        query = build_query(sentence)
        if query:
            candidates.append((sentence, query, reason))

    if not candidates:
        return

    def _build_cits(papers):
        cits = []
        for paper in papers:
            formatted = fmt_fn(paper)
            ext_ids = paper.get('externalIds') or {}
            doi = ext_ids.get('DOI', '')
            url = paper.get('url', '')
            if doi:
                doi_valid = validate_doi(doi)
                if not url:
                    url = f"https://doi.org/{doi}" if doi_valid else ''
            else:
                doi_valid = None
            oa_pdf = paper.get('openAccessPdf') or {}
            cits.append({
                'formatted': formatted, 'bibtex': format_bibtex(paper),
                'ris': format_ris(paper), 'title': paper.get('title', ''),
                'year': paper.get('year'), 'venue': paper.get('venue', ''),
                'doi': doi, 'doi_valid': doi_valid,
                'url': url, 'pdf_url': oa_pdf.get('url', ''),
                'citation_count': paper.get('citationCount'),
                'abstract': paper.get('abstract') or '',
            })
        return cits

    def _worker(item):
        sentence, query, reason = item
        papers = search_papers(
            query, year_range=year_range, sources=sources, limit=fetch_limit,
            open_access_only=open_access_only, fields_of_study=fields_of_study,
            min_citation_count=min_citation_count, sort_by=sort_by,
        )
        return sentence, query, reason, papers[:results_per_sentence]

    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
        future_to_idx = {pool.submit(_worker, c): i for i, c in enumerate(candidates)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                sentence, query, reason, papers = future.result()
                citations = _build_cits(papers)
                if citations:
                    yield idx, {'sentence': sentence, 'query': query, 'reason': reason, 'citations': citations}
            except Exception:
                pass
