"""
Core citation search logic using Semantic Scholar API.
"""

import re
import requests
from typing import Optional

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

# Patterns that signal a claim needing citation
CITATION_INDICATORS = [
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
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CITATION_INDICATORS]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def needs_citation(sentence: str) -> bool:
    """Return True if the sentence likely needs a citation."""
    # Skip sentences that already have citations like [1], (Smith, 2020), etc.
    if re.search(r'\[\d+\]|\(\w+,?\s*\d{4}\)', sentence):
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


def format_apa(paper: dict) -> str:
    """Format a Semantic Scholar paper result as APA citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')

    if not authors:
        author_str = 'Unknown Author'
    elif len(authors) == 1:
        name = authors[0].get('name', '')
        parts = name.split()
        if parts:
            last = parts[-1]
            initials = ' '.join(p[0] + '.' for p in parts[:-1] if p)
            author_str = f"{last}, {initials}".strip(', ')
        else:
            author_str = name
    elif len(authors) <= 6:
        formatted = []
        for a in authors:
            name = a.get('name', '')
            parts = name.split()
            if parts:
                last = parts[-1]
                initials = ' '.join(p[0] + '.' for p in parts[:-1] if p)
                formatted.append(f"{last}, {initials}".strip(', '))
            else:
                formatted.append(name)
        author_str = ', '.join(formatted[:-1]) + ', & ' + formatted[-1] if len(formatted) > 1 else formatted[0]
    else:
        name = authors[0].get('name', '')
        parts = name.split()
        if parts:
            last = parts[-1]
            initials = ' '.join(p[0] + '.' for p in parts[:-1] if p)
            first_author = f"{last}, {initials}".strip(', ')
        else:
            first_author = name
        author_str = f"{first_author}, et al."

    venue_str = f" *{venue}*." if venue else '.'
    return f"{author_str} ({year}). {title}{venue_str}"


def format_mla(paper: dict) -> str:
    """Format a Semantic Scholar paper result as MLA citation."""
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    title = paper.get('title', 'Untitled')
    venue = paper.get('venue', '')

    if not authors:
        author_str = 'Unknown Author'
    elif len(authors) == 1:
        name = authors[0].get('name', '')
        parts = name.split()
        if len(parts) >= 2:
            author_str = f"{parts[-1]}, {' '.join(parts[:-1])}"
        else:
            author_str = name
    else:
        name = authors[0].get('name', '')
        parts = name.split()
        if len(parts) >= 2:
            first = f"{parts[-1]}, {' '.join(parts[:-1])}"
        else:
            first = name
        author_str = first + ', et al.'

    venue_str = f" *{venue}*," if venue else ','
    return f"{author_str}. \"{title}.\"{ venue_str} {year}."


def search_papers(
    query: str,
    year_range: Optional[tuple[int, int]] = None,
    sources: Optional[list[str]] = None,
    limit: int = 5,
) -> list[dict]:
    """Search Semantic Scholar for papers matching query."""
    params = {
        'query': query,
        'limit': limit,
        'fields': 'title,authors,year,venue,externalIds,abstract,url',
    }
    if year_range:
        params['year'] = f"{year_range[0]}-{year_range[1]}"

    try:
        resp = requests.get(SEMANTIC_SCHOLAR_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        papers = data.get('data', [])

        # Filter by source/venue if specified
        if sources:
            src_lower = [s.lower() for s in sources]
            papers = [
                p for p in papers
                if any(s in (p.get('venue') or '').lower() for s in src_lower)
            ] or papers  # fall back to all if none match

        return papers
    except requests.RequestException:
        return []


def find_citations_for_text(
    text: str,
    citation_format: str = 'apa',
    year_range: Optional[tuple[int, int]] = None,
    sources: Optional[list[str]] = None,
    results_per_sentence: int = 3,
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
    sentences = split_sentences(text)
    results = []

    for sentence in sentences:
        if not needs_citation(sentence):
            continue

        query = build_query(sentence)
        if not query:
            continue

        papers = search_papers(query, year_range=year_range, sources=sources, limit=results_per_sentence)
        citations = []
        for paper in papers:
            if citation_format == 'mla':
                formatted = format_mla(paper)
            else:
                formatted = format_apa(paper)

            url = paper.get('url', '')
            ext_ids = paper.get('externalIds') or {}
            doi = ext_ids.get('DOI', '')
            if doi and not url:
                url = f"https://doi.org/{doi}"

            citations.append({
                'formatted': formatted,
                'title': paper.get('title', ''),
                'year': paper.get('year'),
                'venue': paper.get('venue', ''),
                'url': url,
                'abstract': (paper.get('abstract') or '')[:300],
            })

        if citations:
            results.append({
                'sentence': sentence,
                'query': query,
                'citations': citations,
            })

    return results
