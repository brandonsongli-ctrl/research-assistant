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
    r'\b\d+\s*%\b',
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

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CITATION_INDICATORS]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def needs_citation(sentence: str) -> bool:
    """Return True if the sentence likely needs a citation."""
    # Skip sentences that already have citations like [1], (Smith, 2020), ^1, etc.
    if re.search(r'\[\d+\]|\(\w[\w\s]*,?\s*\d{4}\)|\^\d+|ibid\.|op\.\s*cit\.', sentence, re.IGNORECASE):
        return False
    for pattern in COMPILED_PATTERNS:
        if pattern.search(sentence):
            return True
    return False


def build_query(sentence: str) -> str:
    """Extract key terms from sentence for search query."""
    # Remove common stop words and short words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'can', 'it', 'its',
        'this', 'that', 'these', 'those', 'not', 'also', 'which', 'who',
        'studies', 'research', 'show', 'shows', 'shown', 'suggest', 'suggests',
        'evidence', 'data', 'indicates', 'indicate', 'demonstrate', 'demonstrates',
        'according', 'generally', 'commonly', 'widely', 'significant', 'significantly',
    }
    words = re.findall(r'\b[a-zA-Z]{3,}\b', sentence)
    keywords = [w for w in words if w.lower() not in stop_words]
    # Take the most meaningful 6 words
    return ' '.join(keywords[:6])


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


def search_papers(
    query: str,
    year_range: Optional[tuple[int, int]] = None,
    sources: Optional[list[str]] = None,
    limit: int = 5,
    open_access_only: bool = False,
    fields_of_study: Optional[list[str]] = None,
) -> list[dict]:
    """Search Semantic Scholar for papers matching query."""
    cache_key = (query, year_range, tuple(sources or []), limit, open_access_only, tuple(fields_of_study or []))
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

        # Sort by citation count descending (papers without count ranked last)
        papers.sort(key=lambda p: p.get('citationCount') or 0, reverse=True)

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

    # Collect candidate (sentence, query) pairs preserving order
    candidates = []
    for sentence in split_sentences(text):
        if not needs_citation(sentence):
            continue
        query = build_query(sentence)
        if query:
            candidates.append((sentence, query))

    if not candidates:
        return []

    def _fetch(sentence_query):
        sentence, query = sentence_query
        papers = search_papers(
            query,
            year_range=year_range,
            sources=sources,
            limit=fetch_limit,
            open_access_only=open_access_only,
            fields_of_study=fields_of_study,
        )
        return sentence, query, papers[:results_per_sentence]

    # Fire all queries in parallel (up to 8 workers)
    ordered: dict[int, tuple] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
        future_to_idx = {pool.submit(_fetch, c): i for i, c in enumerate(candidates)}
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
            url = paper.get('url', '')
            ext_ids = paper.get('externalIds') or {}
            doi = ext_ids.get('DOI', '')
            if doi and not url:
                url = f"https://doi.org/{doi}"
            oa_pdf = paper.get('openAccessPdf') or {}
            pdf_url = oa_pdf.get('url', '')
            citations.append({
                'formatted': formatted,
                'bibtex': format_bibtex(paper),
                'title': paper.get('title', ''),
                'year': paper.get('year'),
                'venue': paper.get('venue', ''),
                'url': url,
                'pdf_url': pdf_url,
                'citation_count': paper.get('citationCount'),
                'abstract': (paper.get('abstract') or '')[:300],
            })
        return citations

    results = []
    for idx in sorted(ordered):
        sentence, query, papers = ordered[idx]
        citations = _build_citations(papers)
        if citations:
            results.append({'sentence': sentence, 'query': query, 'citations': citations})

    return results
