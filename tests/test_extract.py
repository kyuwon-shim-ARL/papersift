"""Unit tests for extract.py (LLM extraction prompt builder and response parser)."""

import json
import pytest
from pathlib import Path
from papersift.extract import (
    EXTRACTION_PROMPT_TEMPLATE,
    build_batch_prompts,
    parse_llm_response,
    merge_extractions,
    load_extractions,
    save_prompts,
    filter_extraction_quality,
)


def test_build_batch_prompts_basic():
    """Produces correct number of prompts for given papers."""
    papers = [{"doi": f"10.1/{i}", "title": f"Paper {i}", "year": 2024, "abstract": f"Abstract {i}"} for i in range(10)]
    prompts, doi_lists = build_batch_prompts(papers, batch_size=45)
    assert len(prompts) == 1
    assert len(doi_lists) == 1
    assert len(doi_lists[0]) == 10


def test_build_batch_prompts_batch_size():
    """Custom batch_size is respected."""
    papers = [{"doi": f"10.1/{i}", "title": f"P{i}", "year": 2024, "abstract": f"A{i}"} for i in range(10)]
    prompts, doi_lists = build_batch_prompts(papers, batch_size=3)
    assert len(prompts) == 4  # ceil(10/3) = 4
    assert len(doi_lists[0]) == 3
    assert len(doi_lists[1]) == 3
    assert len(doi_lists[2]) == 3
    assert len(doi_lists[3]) == 1


def test_build_batch_prompts_includes_paper_info():
    """Each prompt contains DOI, title, abstract."""
    papers = [{"doi": "10.1/test", "title": "Test Title", "year": 2024, "abstract": "Test abstract text"}]
    prompts, _ = build_batch_prompts(papers)
    assert "10.1/test" in prompts[0]
    assert "Test Title" in prompts[0]
    assert "Test abstract text" in prompts[0]


def test_build_batch_prompts_no_abstract():
    """Papers without abstract get '(no abstract available)'."""
    papers = [{"doi": "10.1/test", "title": "Title", "year": 2024}]
    prompts, _ = build_batch_prompts(papers)
    assert "(no abstract available)" in prompts[0]

    # Also test empty string abstract
    papers2 = [{"doi": "10.1/test2", "title": "Title2", "year": 2024, "abstract": ""}]
    prompts2, _ = build_batch_prompts(papers2)
    assert "(no abstract available)" in prompts2[0]


def test_build_batch_prompts_doi_tracking():
    """batch_doi_lists correctly maps to prompts."""
    papers = [{"doi": f"10.1/{i}", "title": f"P{i}", "year": 2024, "abstract": ""} for i in range(5)]
    prompts, doi_lists = build_batch_prompts(papers, batch_size=2)
    assert doi_lists[0] == ["10.1/0", "10.1/1"]
    assert doi_lists[1] == ["10.1/2", "10.1/3"]
    assert doi_lists[2] == ["10.1/4"]


def test_build_batch_prompts_skips_no_doi():
    """Papers without DOI are skipped."""
    papers = [
        {"doi": "10.1/a", "title": "A", "year": 2024},
        {"title": "No DOI", "year": 2024},  # no doi
        {"doi": "", "title": "Empty DOI", "year": 2024},  # empty doi
        {"doi": "10.1/b", "title": "B", "year": 2024},
    ]
    prompts, doi_lists = build_batch_prompts(papers)
    assert len(doi_lists[0]) == 2  # only papers with doi
    assert "10.1/a" in doi_lists[0]
    assert "10.1/b" in doi_lists[0]


def test_parse_llm_response_clean_json():
    """Parse well-formed JSON array."""
    response = json.dumps([
        {"doi": "10.1/a", "problem": "P1", "method": "M1", "finding": "F1"},
        {"doi": "10.1/b", "problem": "P2", "method": "M2", "finding": "F2"},
    ])
    result = parse_llm_response(response)
    assert len(result) == 2
    assert result[0]["doi"] == "10.1/a"
    assert result[1]["finding"] == "F2"


def test_parse_llm_response_markdown_wrapped():
    """Parse JSON inside ```json ... ```."""
    response = '```json\n[{"doi": "10.1/a", "problem": "P", "method": "M", "finding": "F"}]\n```'
    result = parse_llm_response(response)
    assert len(result) == 1
    assert result[0]["doi"] == "10.1/a"


def test_parse_llm_response_extra_text():
    """Parse JSON with preamble/postamble text."""
    response = 'Here are the results:\n\n[{"doi": "10.1/a", "problem": "P", "method": "M", "finding": "F"}]\n\nI hope this helps!'
    result = parse_llm_response(response)
    assert len(result) == 1
    assert result[0]["doi"] == "10.1/a"


def test_parse_llm_response_malformed():
    """Returns empty list on unparseable input."""
    result = parse_llm_response("This is not JSON at all")
    assert result == []


def test_merge_extractions_basic():
    """Fields correctly attached to papers."""
    papers = [
        {"doi": "10.1/a", "title": "A"},
        {"doi": "10.1/b", "title": "B"},
    ]
    extractions = [
        {"doi": "10.1/a", "problem": "P1", "method": "M1", "finding": "F1"},
        {"doi": "10.1/b", "problem": "P2", "method": "M2", "finding": "F2"},
    ]
    result = merge_extractions(papers, extractions)
    assert result[0]["problem"] == "P1"
    assert result[1]["method"] == "M2"


def test_merge_extractions_case_insensitive():
    """DOI matching is case-insensitive."""
    papers = [{"doi": "10.1234/ABC", "title": "Test"}]
    extractions = [{"doi": "10.1234/abc", "problem": "P", "method": "M", "finding": "F"}]
    result = merge_extractions(papers, extractions)
    assert result[0]["problem"] == "P"


def test_merge_extractions_missing_papers():
    """Papers without extraction get empty strings."""
    papers = [
        {"doi": "10.1/a", "title": "A"},
        {"doi": "10.1/b", "title": "B"},
    ]
    extractions = [{"doi": "10.1/a", "problem": "P", "method": "M", "finding": "F"}]
    result = merge_extractions(papers, extractions)
    assert result[0]["problem"] == "P"
    assert result[1]["problem"] == ""
    assert result[1]["method"] == ""
    assert result[1]["finding"] == ""


def test_load_extractions_list_format(tmp_path):
    """Load from list-format JSON."""
    data = [
        {"doi": "10.1/a", "problem": "P", "method": "M", "finding": "F"},
    ]
    p = tmp_path / "ext.json"
    p.write_text(json.dumps(data))
    result = load_extractions(p)
    assert len(result) == 1
    assert result[0]["doi"] == "10.1/a"


def test_load_extractions_dict_format(tmp_path):
    """Load from dict-format JSON."""
    data = {
        "10.1/a": {"problem": "P", "method": "M", "finding": "F"},
    }
    p = tmp_path / "ext.json"
    p.write_text(json.dumps(data))
    result = load_extractions(p)
    assert len(result) == 1
    assert result[0]["doi"] == "10.1/a"
    assert result[0]["problem"] == "P"


def test_prompt_template_has_placeholders():
    """EXTRACTION_PROMPT_TEMPLATE contains {papers_block}."""
    assert "{papers_block}" in EXTRACTION_PROMPT_TEMPLATE


def test_parse_llm_response_extended_fields():
    """Parse all 7 fields correctly."""
    response = json.dumps([
        {
            "doi": "10.1/a",
            "problem": "P1",
            "method": "M1",
            "finding": "F1",
            "dataset": "D1",
            "metric": "AUC=0.95",
            "baseline": "RF",
            "result": "2.3x speedup"
        },
    ])
    result = parse_llm_response(response)
    assert len(result) == 1
    assert result[0]["doi"] == "10.1/a"
    assert result[0]["problem"] == "P1"
    assert result[0]["method"] == "M1"
    assert result[0]["finding"] == "F1"
    assert result[0]["dataset"] == "D1"
    assert result[0]["metric"] == "AUC=0.95"
    assert result[0]["baseline"] == "RF"
    assert result[0]["result"] == "2.3x speedup"


def test_parse_llm_response_missing_new_fields():
    """New fields default to empty string when absent (backward compat)."""
    response = json.dumps([
        {"doi": "10.1/a", "problem": "P", "method": "M", "finding": "F"},
    ])
    result = parse_llm_response(response)
    assert len(result) == 1
    assert result[0]["doi"] == "10.1/a"
    assert result[0]["problem"] == "P"
    assert result[0]["method"] == "M"
    assert result[0]["finding"] == "F"
    # New fields should default to empty string
    assert result[0]["dataset"] == ""
    assert result[0]["metric"] == ""
    assert result[0]["baseline"] == ""
    assert result[0]["result"] == ""


def test_merge_extractions_extended_fields():
    """All 7 fields merged into papers."""
    papers = [
        {"doi": "10.1/a", "title": "A"},
        {"doi": "10.1/b", "title": "B"},
    ]
    extractions = [
        {
            "doi": "10.1/a",
            "problem": "P1",
            "method": "M1",
            "finding": "F1",
            "dataset": "E. coli",
            "metric": "AUC",
            "baseline": "null model",
            "result": "p<0.001"
        },
        {
            "doi": "10.1/b",
            "problem": "P2",
            "method": "M2",
            "finding": "F2",
            "dataset": "MNIST",
            "metric": "RMSE",
            "baseline": "RF",
            "result": "0.95"
        },
    ]
    result = merge_extractions(papers, extractions)
    assert result[0]["problem"] == "P1"
    assert result[0]["dataset"] == "E. coli"
    assert result[0]["metric"] == "AUC"
    assert result[0]["baseline"] == "null model"
    assert result[0]["result"] == "p<0.001"
    assert result[1]["method"] == "M2"
    assert result[1]["dataset"] == "MNIST"
    assert result[1]["baseline"] == "RF"


def test_filter_extraction_quality_truncation():
    """Long fields are truncated at word boundary."""
    long_text = "This is a very long sentence. " * 20  # ~600 chars
    extractions = [
        {
            "doi": "10.1/a",
            "problem": "Short",
            "method": long_text,
            "finding": "Short",
            "dataset": "",
            "metric": "",
            "baseline": "",
            "result": ""
        }
    ]
    result = filter_extraction_quality(extractions, max_field_length=200)
    assert len(result[0]["method"]) <= 204  # 200 + "..."
    assert result[0]["method"].endswith("...")
    assert "_quality_flags" in result[0]
    assert "method_truncated" in result[0]["_quality_flags"]
    # Short fields untouched
    assert result[0]["problem"] == "Short"
    assert "problem_truncated" not in result[0].get("_quality_flags", [])


def test_filter_extraction_quality_short_fields():
    """Short fields are untouched."""
    extractions = [
        {
            "doi": "10.1/a",
            "problem": "P",
            "method": "M",
            "finding": "F",
            "dataset": "D",
            "metric": "AUC",
            "baseline": "RF",
            "result": "0.95"
        }
    ]
    result = filter_extraction_quality(extractions, max_field_length=200)
    assert result[0]["problem"] == "P"
    assert result[0]["method"] == "M"
    assert result[0]["finding"] == "F"
    assert result[0]["dataset"] == "D"
    assert "_quality_flags" not in result[0]


def test_prompt_template_has_new_fields():
    """Template mentions dataset, metric, baseline, result."""
    assert "dataset" in EXTRACTION_PROMPT_TEMPLATE
    assert "metric" in EXTRACTION_PROMPT_TEMPLATE
    assert "baseline" in EXTRACTION_PROMPT_TEMPLATE
    assert "result" in EXTRACTION_PROMPT_TEMPLATE
