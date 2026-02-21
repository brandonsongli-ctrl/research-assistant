"""
Research Assistant - Citation Finder Web Application.
Identifies sentences needing citations and finds supporting papers.
"""

from flask import Flask, render_template, request, jsonify
from citation_finder import find_citations_for_text

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/find-citations', methods=['POST'])
def find_citations():
    data = request.get_json(force=True)

    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'No text provided.'}), 400

    citation_format = data.get('format', 'apa').lower()
    if citation_format not in ('apa', 'mla', 'chicago', 'ieee', 'harvard', 'vancouver', 'bibtex'):
        citation_format = 'apa'

    # Year range
    year_start = data.get('year_start')
    year_end = data.get('year_end')
    year_range = None
    if year_start and year_end:
        try:
            year_range = (int(year_start), int(year_end))
        except (ValueError, TypeError):
            year_range = None

    # Sources
    sources_raw = data.get('sources', '')
    sources = None
    if sources_raw:
        sources = [s.strip() for s in sources_raw.split(',') if s.strip()]

    try:
        results_per_sentence = max(1, min(10, int(data.get('results_per_sentence', 3))))
    except (ValueError, TypeError):
        results_per_sentence = 3

    open_access_only = bool(data.get('open_access_only', False))

    results = find_citations_for_text(
        text=text,
        citation_format=citation_format,
        year_range=year_range,
        sources=sources or None,
        results_per_sentence=results_per_sentence,
        open_access_only=open_access_only,
    )

    return jsonify({'results': results})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
