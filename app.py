"""
Research Assistant - Citation Finder Web Application.
Identifies sentences needing citations and finds supporting papers.
"""

import json
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from citation_finder import find_citations_for_text, stream_citations_for_text

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/find-citations', methods=['POST'])
def find_citations():
    data = request.get_json(force=True)
    params = _parse_params(data)
    if not params['text']:
        return jsonify({'error': 'No text provided.'}), 400
    results = find_citations_for_text(**params)
    return jsonify({'results': results})


def _parse_params(data: dict) -> dict:
    """Parse shared request parameters."""
    text = (data.get('text') or '').strip()
    citation_format = data.get('format', 'apa').lower()
    if citation_format not in ('apa', 'mla', 'chicago', 'ieee', 'harvard', 'vancouver', 'bibtex'):
        citation_format = 'apa'
    year_start, year_end = data.get('year_start'), data.get('year_end')
    year_range = None
    if year_start and year_end:
        try:
            year_range = (int(year_start), int(year_end))
        except (ValueError, TypeError):
            pass
    sources_raw = data.get('sources', '')
    sources = [s.strip() for s in sources_raw.split(',') if s.strip()] if sources_raw else None
    try:
        rps = max(1, min(10, int(data.get('results_per_sentence', 3))))
    except (ValueError, TypeError):
        rps = 3
    fields_raw = data.get('fields_of_study', '')
    fields_of_study = [f.strip() for f in fields_raw.split(',') if f.strip()] if fields_raw else None
    try:
        min_cit = max(0, int(data.get('min_citation_count', 0)))
    except (ValueError, TypeError):
        min_cit = 0
    sort_by = data.get('sort_by', 'citations')
    if sort_by not in ('citations', 'relevance'):
        sort_by = 'citations'
    return dict(
        text=text, citation_format=citation_format, year_range=year_range,
        sources=sources, results_per_sentence=rps, open_access_only=bool(data.get('open_access_only')),
        fields_of_study=fields_of_study, min_citation_count=min_cit, sort_by=sort_by,
    )


@app.route('/api/stream-citations', methods=['POST'])
def stream_citations():
    data = request.get_json(force=True)
    params = _parse_params(data)
    if not params['text']:
        return jsonify({'error': 'No text provided.'}), 400

    def generate():
        collected = {}
        for idx, result in stream_citations_for_text(**params):
            collected[idx] = result
            payload = {'type': 'result', 'index': idx, 'data': result}
            yield f"data: {json.dumps(payload)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
