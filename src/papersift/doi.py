"""DOI normalization, classification, filtering, and deduplication utilities."""

import re
from enum import Enum


def normalize_doi(doi: str) -> str:
    """Normalize DOI to bare form without URL prefix.

    Examples:
        '10.1038/xxx' -> '10.1038/xxx'
        'https://doi.org/10.1038/xxx' -> '10.1038/xxx'
        'http://doi.org/10.1038/xxx' -> '10.1038/xxx'
    """
    if not doi:
        return doi
    for prefix in ('https://doi.org/', 'http://doi.org/'):
        if doi.startswith(prefix):
            return doi[len(prefix):]
    return doi


# ---------------------------------------------------------------------------
# DOI Type Classification
# ---------------------------------------------------------------------------

class DoiType(Enum):
    """Classification of DOI types."""
    JOURNAL = "journal"
    PREPRINT = "preprint"
    DATASET = "dataset"
    SUPPLEMENTARY = "supplementary"
    EDITORIAL = "editorial"
    CONFERENCE_ABSTRACT = "conference_abstract"
    BOOK_CHAPTER = "book_chapter"
    OTHER = "other"


# Regex patterns for supplementary / editorial suffix detection.
# Matches patterns like .s001, _suppl, _suppl1, .supp1, and also bare s1/s2
# directly appended (e.g., ALTEX DOIs: 10.14573/altex.1812101s1).
_SUPPL_SUFFIX_RE = re.compile(
    r'\.s\d{3,4}$'        # .s001, .s002, .s0001 etc.
    r'|_suppl\d*$'         # _suppl, _suppl1, _suppl2
    r'|\.supp\d*$'         # .supp, .supp1
    r'|(?<=[a-z\d])s\d{1,2}$',  # bare s1, s2 appended to alphanumeric
    re.IGNORECASE,
)

_EDITORIAL_SUFFIX_RE = re.compile(
    r'\.sa\d+$',           # eLife decision letters / author responses .sa1, .sa2
    re.IGNORECASE,
)

# eLife sub-article pattern: 10.7554/elife.NNNNN.NNN where the last segment
# has more than 2 digits, indicating a sub-article (figure supplement, etc.)
_ELIFE_SUBARTICLE_RE = re.compile(
    r'^10\.7554/elife\.\d+\.\d{3,}$',
    re.IGNORECASE,
)

# bioRxiv / medRxiv DOI patterns (10.1101/ prefix).
# bioRxiv: 10.1101/YYYY.MM.DD.NNNNNN or 10.1101/NNNNNN (6+ digits)
# Cold Spring Harbor published journals use different patterns.
_BIORXIV_RE = re.compile(
    r'^10\.1101/'
    r'(?:'
    r'\d{4}\.\d{2}\.\d{2}\.\d+'   # date-based: YYYY.MM.DD.NNNNNN
    r'|\d{6,}'                      # legacy 6+ digit preprint ID
    r')$',
    re.IGNORECASE,
)

# Known preprint server DOI prefixes (checked after bioRxiv special handling)
_PREPRINT_PREFIXES: list[tuple[str, re.Pattern[str] | None]] = [
    # arXiv
    ('10.48550/arxiv.', None),
    # SSRN
    ('10.2139/ssrn.', None),
    # ChemRxiv (old prefix)
    ('10.26434/chemrxiv', None),
    # ChemRxiv (new ACS prefix)
    ('10.26434/chemrxiv-', None),
    # Research Square
    ('10.21203/rs.', None),
    # OSF Preprints
    ('10.31219/osf.io/', None),
    # PeerJ Preprints
    ('10.7287/peerj.preprints.', None),
    # Preprints.org
    ('10.20944/preprints', None),
    # EarthArXiv
    ('10.31223/', None),
    # SocArXiv
    ('10.31235/osf.io/', None),
    # engrXiv
    ('10.31224/osf.io/', None),
    # Morressier
    ('10.26226/morressier.', None),
]

# Known dataset repository DOI prefixes
_DATASET_PREFIXES: list[str] = [
    '10.5281/zenodo.',             # Zenodo
    '10.6084/m9.figshare.',        # Figshare
    '10.17632/',                   # Mendeley Data
    '10.17605/osf.io/',            # OSF
    '10.5061/dryad.',              # Dryad
    '10.5523/bris.',               # University of Bristol
    '10.5518/',                    # University of Leeds
    '10.4233/uuid:',               # TU Delft
    '10.24355/dbbs.',              # TU Braunschweig
    '10.7910/dvn/',                # Harvard Dataverse
    '10.5282/edm/',                # LMU Munich
    '10.15468/',                   # GBIF
    '10.48321/',                   # Pangaea
    '10.22032/dbt.',               # University of Bern
    '10.26153/tsw/',               # Texas ScholarWorks
    '10.14264/',                   # University of Queensland
]

# Faculty Opinions / F1000 editorial DOI prefixes
_EDITORIAL_PREFIXES: list[str] = [
    '10.3410/f.',                  # F1000 / Faculty Opinions
    '10.5256/f1000research.',      # F1000Research (review reports)
    '10.7490/f1000research.',      # F1000Research (posters/slides)
]

# Book chapter DOI patterns
_BOOK_CHAPTER_RE = re.compile(
    r'^10\.1007/978-'              # Springer book chapters (ISBN-based)
    r'|^10\.1016/[bB]978-'        # Elsevier book chapters
    r'|^10\.1201/'                 # CRC Press / Taylor & Francis books
    r'|^10\.1002/978'             # Wiley book chapters
    r'|^10\.1515/978'             # De Gruyter book chapters
    r'|^10\.4018/978-',           # IGI Global book chapters
    re.IGNORECASE,
)

# Conference abstract pattern: _suppl in DOI (journal supplement issue)
_CONFERENCE_ABSTRACT_RE = re.compile(
    r'_suppl\d*\b.*\d',           # e.g. 10.xxxx/journal_suppl1.P123
    re.IGNORECASE,
)

# DOI registrar prefix length heuristic: well-known journal publishers
# typically have 4-digit registrar codes (e.g. 10.1038, 10.1016).
# 5+ digit registrar codes are often newer data repositories or
# less-established registrars. We classify these as OTHER when no
# specific pattern matches.
_HIGH_REGISTRAR_RE = re.compile(r'^10\.\d{5,}/')


def classify_doi(doi: str) -> DoiType:
    """Classify a DOI into a type category.

    Classification order (most specific first):
    1. Supplementary suffix patterns (.s001, _suppl, s1/s2 etc.)
    2. Editorial suffix patterns (.sa1, .sa2)
    3. Editorial prefixes (F1000, etc.)
    4. Dataset repository prefixes
    5. Preprint server prefixes (including bioRxiv special handling)
    6. eLife sub-article pattern
    7. Book chapter pattern
    8. High-registrar heuristic (5+ digit prefix -> OTHER)
    9. Default: JOURNAL

    Args:
        doi: A bare DOI string (without URL prefix). Will be normalized
             if URL prefix is present.

    Returns:
        DoiType enum value.
    """
    if not doi:
        return DoiType.OTHER

    doi = normalize_doi(doi).strip()
    doi_lower = doi.lower()

    # --- 1. Supplementary suffix patterns ---
    if _SUPPL_SUFFIX_RE.search(doi_lower):
        return DoiType.SUPPLEMENTARY

    # --- 2. Editorial suffix patterns ---
    if _EDITORIAL_SUFFIX_RE.search(doi_lower):
        return DoiType.EDITORIAL

    # --- 3. Editorial prefixes (F1000, etc.) ---
    for prefix in _EDITORIAL_PREFIXES:
        if doi_lower.startswith(prefix):
            return DoiType.EDITORIAL

    # --- 4. Dataset repository prefixes ---
    for prefix in _DATASET_PREFIXES:
        if doi_lower.startswith(prefix):
            return DoiType.DATASET

    # --- 5. Preprint server prefixes ---
    # bioRxiv / medRxiv special handling (10.1101/ prefix)
    if doi_lower.startswith('10.1101/'):
        if _BIORXIV_RE.match(doi_lower):
            return DoiType.PREPRINT
        # Non-matching 10.1101/ DOIs are CSHL published papers -> JOURNAL
        # (fall through to default)
    else:
        for prefix, pattern in _PREPRINT_PREFIXES:
            if doi_lower.startswith(prefix):
                if pattern is None or pattern.match(doi_lower):
                    return DoiType.PREPRINT

    # --- 6. eLife sub-article pattern ---
    if _ELIFE_SUBARTICLE_RE.match(doi_lower):
        return DoiType.EDITORIAL

    # --- 7. Book chapter pattern ---
    if _BOOK_CHAPTER_RE.match(doi_lower):
        return DoiType.BOOK_CHAPTER

    # --- 8. High-registrar heuristic ---
    # DOIs with 5+ digit registrar prefixes that haven't matched any known
    # pattern are likely data repositories or uncommon registrars.
    if _HIGH_REGISTRAR_RE.match(doi_lower):
        return DoiType.OTHER

    # --- 9. Default ---
    return DoiType.JOURNAL


# ---------------------------------------------------------------------------
# Non-Paper Filter
# ---------------------------------------------------------------------------

_RESEARCH_TYPES = frozenset({DoiType.JOURNAL, DoiType.PREPRINT, DoiType.BOOK_CHAPTER})


def is_research_paper(doi: str) -> bool:
    """Check whether a DOI represents actual research content.

    Returns True for JOURNAL, PREPRINT, and BOOK_CHAPTER types.
    Returns False for DATASET, SUPPLEMENTARY, EDITORIAL,
    CONFERENCE_ABSTRACT, and OTHER types.

    Args:
        doi: A bare or URL-prefixed DOI string.

    Returns:
        True if the DOI likely points to a research paper.
    """
    return classify_doi(doi) in _RESEARCH_TYPES


# ---------------------------------------------------------------------------
# Title Normalization & Matching for Deduplication
# ---------------------------------------------------------------------------

# Common noise words that differ between preprint and published versions
_TITLE_NOISE_WORDS = frozenset({
    'preprint', 'published', 'version', 'revised', 'updated',
    'v1', 'v2', 'v3', 'v4',
})


def _normalize_title(title: str) -> list[str]:
    """Normalize a paper title into a bag of words for comparison.

    Lowercases, strips punctuation, removes common noise words that
    differ between preprint and published versions, splits on whitespace.

    Args:
        title: Raw title string.

    Returns:
        List of normalized words (order preserved, noise words removed).
    """
    if not title:
        return []
    cleaned = re.sub(r'[^\w\s]', '', title.lower())
    words = [w for w in cleaned.split() if w not in _TITLE_NOISE_WORDS]
    return words


def _titles_match(title_a: str, title_b: str, threshold: float = 0.85) -> bool:
    """Check if two paper titles likely refer to the same work.

    Uses a combined similarity strategy:
    - Jaccard similarity (intersection/union) >= threshold, OR
    - Containment similarity (intersection/min_size) >= threshold,
      provided at least 2 meaningful words overlap.

    This handles the common case where a published title is a longer
    version of the preprint title (e.g., adding "predicts in vivo
    cell-type-specific dynamics" to the end).

    Args:
        title_a: First title.
        title_b: Second title.
        threshold: Minimum similarity to consider titles matching.

    Returns:
        True if the titles likely refer to the same work.
    """
    words_a = set(_normalize_title(title_a))
    words_b = set(_normalize_title(title_b))
    if not words_a or not words_b:
        return False

    intersection = words_a & words_b
    if len(intersection) < 2:
        return False

    union = words_a | words_b
    jaccard = len(intersection) / len(union)
    if jaccard >= threshold:
        return True

    # Containment: fraction of the smaller set that appears in the larger
    containment = len(intersection) / min(len(words_a), len(words_b))
    return containment >= threshold


_DEDUP_SIMILARITY_THRESHOLD = 0.85


def deduplicate_preprints(
    papers: list[dict],
    title_key: str = "title",
    doi_key: str = "doi",
    similarity_threshold: float = _DEDUP_SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Remove preprint versions when a published journal version exists.

    For each paper classified as PREPRINT, checks whether any JOURNAL paper
    in the list has a sufficiently similar title. Uses both Jaccard and
    containment similarity to handle cases where the published title is
    an extended version of the preprint title.

    Args:
        papers: List of paper dicts, each containing at least a title
                and doi field.
        title_key: Key used to access the title in paper dicts.
        doi_key: Key used to access the DOI in paper dicts.
        similarity_threshold: Minimum similarity to consider
                              titles as matching. Defaults to 0.85.

    Returns:
        Deduplicated list of paper dicts with preprint duplicates removed.
    """
    if not papers:
        return []

    # Separate papers by type
    preprints: list[tuple[int, dict]] = []
    journals: list[tuple[int, dict]] = []

    for idx, paper in enumerate(papers):
        doi = paper.get(doi_key, "") or ""
        doi_type = classify_doi(doi)
        if doi_type == DoiType.PREPRINT:
            preprints.append((idx, paper))
        elif doi_type == DoiType.JOURNAL:
            journals.append((idx, paper))

    # Find preprints that have a matching journal publication
    preprint_indices_to_remove: set[int] = set()

    for p_idx, preprint in preprints:
        p_title = preprint.get(title_key, "") or ""
        if not p_title:
            continue
        for _, journal in journals:
            j_title = journal.get(title_key, "") or ""
            if not j_title:
                continue
            if _titles_match(p_title, j_title, threshold=similarity_threshold):
                preprint_indices_to_remove.add(p_idx)
                break  # Found a match; no need to check more journals

    # Rebuild list without removed preprints
    return [
        paper for idx, paper in enumerate(papers)
        if idx not in preprint_indices_to_remove
    ]


# ---------------------------------------------------------------------------
# Comprehensive Filtering
# ---------------------------------------------------------------------------

# Mapping from DoiType to the stats key used in removal counts
_REMOVAL_KEY_MAP: dict[DoiType, str] = {
    DoiType.DATASET: "datasets",
    DoiType.SUPPLEMENTARY: "supplementary",
    DoiType.EDITORIAL: "editorial",
    DoiType.CONFERENCE_ABSTRACT: "conference_abstract",
    DoiType.OTHER: "other",
}


def clean_papers(
    papers: list[dict],
    remove_non_papers: bool = True,
    dedupe_preprints: bool = True,
    title_key: str = "title",
    doi_key: str = "doi",
) -> tuple[list[dict], dict]:
    """Filter and deduplicate a list of papers based on DOI classification.

    Applies two independent cleaning steps:
    1. Remove non-research DOIs (datasets, supplementary, editorial, etc.)
    2. Deduplicate preprints that have a published journal version

    Args:
        papers: List of paper dicts.
        remove_non_papers: If True, remove DATASET, SUPPLEMENTARY,
                           EDITORIAL, CONFERENCE_ABSTRACT, and OTHER DOIs.
        dedupe_preprints: If True, remove preprint versions when a
                          published journal version with matching title exists.
        title_key: Key used to access the title in paper dicts.
        doi_key: Key used to access the DOI in paper dicts.

    Returns:
        Tuple of (cleaned_papers, stats_dict).
        stats_dict contains flat keys:
            - total_input: Number of input papers.
            - final_count: Number of output papers.
            - removed_datasets: Count of removed dataset DOIs.
            - removed_supplementary: Count of removed supplementary DOIs.
            - removed_editorial: Count of removed editorial DOIs.
            - removed_conference_abstract: Count of removed conference abstracts.
            - removed_other: Count of removed other DOIs.
            - removed_preprint_duplicates: Count of removed preprint duplicates.
            - doi_types: Dict of DoiType value -> count (over input).
    """
    input_count = len(papers)

    # Classify all DOIs
    doi_types: dict[str, int] = {}
    paper_types: list[DoiType] = []
    for paper in papers:
        doi = paper.get(doi_key, "") or ""
        dtype = classify_doi(doi)
        paper_types.append(dtype)
        type_key = dtype.value
        doi_types[type_key] = doi_types.get(type_key, 0) + 1

    # Initialize removal counters
    removed_datasets = 0
    removed_supplementary = 0
    removed_editorial = 0
    removed_conference_abstract = 0
    removed_other = 0
    removed_preprint_duplicates = 0

    # Step 1: Remove non-research papers
    if remove_non_papers:
        filtered: list[dict] = []
        for paper, dtype in zip(papers, paper_types):
            if dtype == DoiType.DATASET:
                removed_datasets += 1
            elif dtype == DoiType.SUPPLEMENTARY:
                removed_supplementary += 1
            elif dtype == DoiType.EDITORIAL:
                removed_editorial += 1
            elif dtype == DoiType.CONFERENCE_ABSTRACT:
                removed_conference_abstract += 1
            elif dtype == DoiType.OTHER:
                removed_other += 1
            else:
                filtered.append(paper)
        working = filtered
    else:
        working = list(papers)

    # Step 2: Deduplicate preprints
    if dedupe_preprints:
        before_dedup = len(working)
        working = deduplicate_preprints(
            working,
            title_key=title_key,
            doi_key=doi_key,
        )
        removed_preprint_duplicates = before_dedup - len(working)

    output_count = len(working)

    stats: dict = {
        "total_input": input_count,
        "final_count": output_count,
        "removed_datasets": removed_datasets,
        "removed_supplementary": removed_supplementary,
        "removed_editorial": removed_editorial,
        "removed_conference_abstract": removed_conference_abstract,
        "removed_other": removed_other,
        "removed_preprint_duplicates": removed_preprint_duplicates,
        "doi_types": doi_types,
    }

    return working, stats
