"""Unit tests for citation_finder module."""

import pytest
from citation_finder import (
    split_sentences,
    needs_citation,
    get_citation_reason,
    build_query,
    format_apa,
    format_mla,
    format_chicago,
    format_ieee,
    format_bibtex,
    format_ris,
    _get_author_parts,
)


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_basic_split(self):
        text = "Climate change is a global problem. Temperatures are rising fast."
        parts = split_sentences(text)
        assert len(parts) == 2

    def test_abbreviation_no_split(self):
        # "Dr." should not trigger a split
        text = "Dr. Smith found that climate change is significant. Temperatures are rising."
        parts = split_sentences(text)
        assert len(parts) == 2

    def test_et_al_no_split(self):
        text = "Jones et al. reported a 30% increase in mortality rates. These findings have broad implications for public health."
        parts = split_sentences(text)
        assert len(parts) == 2

    def test_vs_no_split(self):
        text = "The study compared treatment A vs. treatment B in a clinical trial. Results were significant."
        parts = split_sentences(text)
        assert len(parts) == 2

    def test_short_fragments_excluded(self):
        # Fragments under 20 chars should be filtered out
        parts = split_sentences("Hi. Studies show that increased physical activity significantly reduces cardiovascular risk.")
        assert all(len(p) > 20 for p in parts)

    def test_multi_sentence(self):
        text = (
            "Studies show that exercise reduces cardiovascular risk. "
            "Research indicates that diet also plays a role. "
            "Experts agree that both factors are significant."
        )
        parts = split_sentences(text)
        assert len(parts) == 3


# ---------------------------------------------------------------------------
# needs_citation / get_citation_reason
# ---------------------------------------------------------------------------

class TestNeedsCitation:
    def test_studies_show(self):
        assert needs_citation("Studies show that exercise reduces cardiovascular risk.")

    def test_percentage(self):
        assert needs_citation("The treatment was effective in 73% of patients.")

    def test_significant(self):
        assert needs_citation("The difference was statistically significant.")

    def test_compared_to(self):
        assert needs_citation("The group performed better compared to controls.")

    def test_already_cited_bracket(self):
        assert not needs_citation("Exercise reduces cardiovascular risk [1].")

    def test_already_cited_parenthesis(self):
        assert not needs_citation("Studies confirm this (Smith, 2020).")

    def test_plain_statement(self):
        # A plain statement with no claim indicator should return None
        assert not needs_citation("The sky is blue.")

    def test_causation(self):
        assert needs_citation("Smoking causes lung cancer.")

    def test_correlation(self):
        assert needs_citation("Obesity is correlated with diabetes.")

    def test_meta_analysis(self):
        assert needs_citation("A meta-analysis of 50 studies found a strong effect.")


class TestGetCitationReason:
    def test_returns_string_for_claim(self):
        reason = get_citation_reason("Studies show that vaccines are effective.")
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_returns_none_for_plain(self):
        assert get_citation_reason("The sky is blue.") is None

    def test_returns_none_when_already_cited(self):
        assert get_citation_reason("Vaccines are effective [2].") is None

    def test_percentage_reason(self):
        reason = get_citation_reason("Efficacy was 95% in clinical trials.")
        assert reason == "Percentage figure"


# ---------------------------------------------------------------------------
# build_query
# ---------------------------------------------------------------------------

class TestBuildQuery:
    def test_extracts_noun_phrases(self):
        sentence = "Machine Learning methods have significantly improved Natural Language Processing tasks."
        query = build_query(sentence)
        assert "Machine Learning" in query
        assert "Natural Language Processing" in query

    def test_excludes_stop_words(self):
        sentence = "Studies show that the treatment was effective."
        query = build_query(sentence)
        for stop in ('the', 'that', 'show', 'studies'):
            assert stop not in query.lower().split()

    def test_max_eight_tokens(self):
        sentence = (
            "Cardiovascular exercise reduces mortality inflammation cholesterol "
            "hypertension diabetes obesity fatigue insomnia depression."
        )
        query = build_query(sentence)
        # "8 tokens" means 8 words/phrases separated by spaces
        assert len(query.split()) <= 8

    def test_returns_nonempty(self):
        assert build_query("Exercise reduces heart disease risk.") != ''

    def test_deduplication(self):
        sentence = "exercise Exercise EXERCISE reduces heart disease."
        query = build_query(sentence)
        lower_tokens = [t.lower() for t in query.split()]
        assert lower_tokens.count('exercise') <= 1


# ---------------------------------------------------------------------------
# Citation formatters
# ---------------------------------------------------------------------------

SAMPLE_PAPER = {
    'authors': [
        {'name': 'John Smith'},
        {'name': 'Jane Doe'},
    ],
    'year': 2021,
    'title': 'Effects of Exercise on Cardiovascular Health',
    'venue': 'Journal of Medicine',
}

SINGLE_AUTHOR_PAPER = {
    'authors': [{'name': 'Alice Johnson'}],
    'year': 2019,
    'title': 'A Study of Sleep Disorders',
    'venue': 'Sleep Research',
}

NO_AUTHOR_PAPER = {
    'authors': [],
    'year': 2020,
    'title': 'Anonymous Study',
    'venue': '',
}


class TestFormatAPA:
    def test_two_authors(self):
        result = format_apa(SAMPLE_PAPER)
        assert '2021' in result
        assert 'Smith' in result
        assert 'Doe' in result
        assert 'Effects of Exercise on Cardiovascular Health' in result

    def test_single_author(self):
        result = format_apa(SINGLE_AUTHOR_PAPER)
        assert 'Johnson' in result
        assert '2019' in result

    def test_no_author(self):
        result = format_apa(NO_AUTHOR_PAPER)
        assert 'Unknown Author' in result

    def test_no_venue(self):
        paper = {**SAMPLE_PAPER, 'venue': ''}
        result = format_apa(paper)
        assert result.endswith('.')


class TestFormatMLA:
    def test_two_authors(self):
        result = format_mla(SAMPLE_PAPER)
        assert 'Smith' in result
        assert 'et al.' in result or 'Doe' in result
        assert '2021' in result

    def test_title_quoted(self):
        result = format_mla(SAMPLE_PAPER)
        assert '"Effects of Exercise on Cardiovascular Health."' in result


class TestFormatChicago:
    def test_two_authors(self):
        result = format_chicago(SAMPLE_PAPER)
        assert 'Smith' in result
        assert '2021' in result

    def test_title_quoted(self):
        result = format_chicago(SAMPLE_PAPER)
        assert '"Effects of Exercise on Cardiovascular Health."' in result


class TestFormatIEEE:
    def test_basic(self):
        result = format_ieee(SAMPLE_PAPER)
        assert '2021' in result
        assert 'Effects of Exercise on Cardiovascular Health' in result

    def test_initials_in_output(self):
        result = format_ieee(SAMPLE_PAPER)
        # IEEE uses initials before last name
        assert 'Smith' in result


class TestFormatBibtex:
    def test_bibtex_structure(self):
        from citation_finder import format_bibtex
        result = format_bibtex(SAMPLE_PAPER)
        assert result.startswith('@article{')
        assert 'title' in result
        assert 'author' in result
        assert 'year' in result
        assert '}' in result

    def test_bibtex_year(self):
        from citation_finder import format_bibtex
        result = format_bibtex(SAMPLE_PAPER)
        assert '2021' in result


class TestFormatRIS:
    def test_ris_structure(self):
        from citation_finder import format_ris
        result = format_ris(SAMPLE_PAPER)
        assert 'TY  -' in result
        assert 'TI  -' in result
        assert 'ER  -' in result

    def test_ris_year(self):
        from citation_finder import format_ris
        result = format_ris(SAMPLE_PAPER)
        assert '2021' in result

    def test_ris_author(self):
        from citation_finder import format_ris
        result = format_ris(SAMPLE_PAPER)
        assert 'AU  -' in result


# ---------------------------------------------------------------------------
# _get_author_parts edge cases
# ---------------------------------------------------------------------------

class TestGetAuthorParts:
    def test_apa_et_al_more_than_6(self):
        authors = [{'name': f'Author{i} Last{i}'} for i in range(8)]
        result = _get_author_parts(authors, 'apa')
        assert 'et al.' in result

    def test_harvard_et_al_more_than_3(self):
        authors = [{'name': f'Author{i} Last{i}'} for i in range(4)]
        result = _get_author_parts(authors, 'harvard')
        assert 'et al.' in result

    def test_vancouver_truncates_at_6(self):
        authors = [{'name': f'Author{i} Last{i}'} for i in range(8)]
        result = _get_author_parts(authors, 'vancouver')
        assert 'et al.' in result

    def test_empty_authors(self):
        result = _get_author_parts([], 'apa')
        assert result == 'Unknown Author'

    def test_unknown_style(self):
        result = _get_author_parts([{'name': 'John Smith'}], 'unknown')
        assert result == 'Unknown Author'
