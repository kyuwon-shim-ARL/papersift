import json
import subprocess
import pytest
from pathlib import Path

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_papers.json")
LANDSCAPE_FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_papers_landscape.json")

def run_cmd(*args, stdin_data=None):
    """Helper to run papersift CLI and return result."""
    result = subprocess.run(
        ["papersift"] + list(args),
        capture_output=True, text=True,
        input=stdin_data,
        timeout=120
    )
    return result

def test_browse_format_json():
    """browse --list --format json outputs valid JSON array."""
    result = run_cmd("browse", FIXTURE, "--list", "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) > 0
    assert 'cluster_id' in data[0]
    assert 'size' in data[0]

def test_find_format_json():
    """find --entity X --format json outputs valid JSON."""
    # First find an entity that exists
    result = run_cmd("find", FIXTURE, "--hubs", "1", "--format", "json")
    assert result.returncode == 0
    hubs = json.loads(result.stdout)
    assert len(hubs) > 0
    # Use first entity from the hub paper
    entity = hubs[0]['entities'][0] if hubs[0].get('entities') else None
    if entity:
        result2 = run_cmd("find", FIXTURE, "--entity", entity, "--format", "json")
        assert result2.returncode == 0
        found = json.loads(result2.stdout)
        assert isinstance(found, list)

def test_filter_by_entity():
    """filter --entity keeps only matching papers."""
    # Find an entity first
    result = run_cmd("find", FIXTURE, "--hubs", "1", "--format", "json")
    hubs = json.loads(result.stdout)
    if hubs and hubs[0].get('entities'):
        entity = hubs[0]['entities'][0]
        result2 = run_cmd("filter", FIXTURE, "--entity", entity)
        assert result2.returncode == 0
        filtered = json.loads(result2.stdout)
        assert isinstance(filtered, list)
        assert len(filtered) > 0
        assert len(filtered) <= 20  # Can't be more than total

def test_filter_by_cluster():
    """filter --cluster extracts papers from specified clusters."""
    result = run_cmd("filter", FIXTURE, "--cluster", "0")
    assert result.returncode == 0
    filtered = json.loads(result.stdout)
    assert isinstance(filtered, list)

def test_filter_exclude():
    """filter --exclude inverts the filter."""
    # Get cluster 0 papers
    r1 = run_cmd("filter", FIXTURE, "--cluster", "0")
    included = json.loads(r1.stdout)

    # Get excluded
    r2 = run_cmd("filter", FIXTURE, "--cluster", "0", "--exclude")
    excluded = json.loads(r2.stdout)

    # Together should equal all papers
    with open(FIXTURE) as f:
        data = json.load(f)
    all_papers = data.get('papers', data) if isinstance(data, dict) else data
    assert len(included) + len(excluded) == len(all_papers)

def test_merge_dedup(tmp_path):
    """merge deduplicates by DOI."""
    output = str(tmp_path / "merged.json")
    result = run_cmd("merge", FIXTURE, FIXTURE, "-o", output)
    assert result.returncode == 0
    with open(output) as f:
        merged = json.load(f)
    # Should be same count as single file (all dupes removed)
    with open(FIXTURE) as f:
        data = json.load(f)
    original = data.get('papers', data) if isinstance(data, dict) else data
    assert len(merged) == len(original)

def test_filter_output_file(tmp_path):
    """filter -o writes to file."""
    output = str(tmp_path / "filtered.json")
    result = run_cmd("filter", FIXTURE, "--cluster", "0", "-o", output)
    assert result.returncode == 0
    assert Path(output).exists()
    with open(output) as f:
        data = json.load(f)
    assert isinstance(data, list)

def test_stdin_invalid_json():
    """Invalid JSON on stdin prints error."""
    result = run_cmd("filter", "-", "--cluster", "0", stdin_data="not json")
    assert result.returncode != 0
    assert "Error" in result.stderr or "error" in result.stderr.lower()
