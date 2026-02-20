"""Tests for DOI normalization and classification."""
from papersift.doi import (
    normalize_doi,
    DoiType,
    classify_doi,
    is_research_paper,
    deduplicate_preprints,
    clean_papers,
)


# ===== DOI NORMALIZATION TESTS =====


def test_bare_doi_passthrough():
    assert normalize_doi("10.1038/nature06244") == "10.1038/nature06244"


def test_https_prefix_stripped():
    assert normalize_doi("https://doi.org/10.1038/nature06244") == "10.1038/nature06244"


def test_http_prefix_stripped():
    assert normalize_doi("http://doi.org/10.1038/nature06244") == "10.1038/nature06244"


def test_empty_string():
    assert normalize_doi("") == ""


def test_special_characters():
    assert normalize_doi("https://doi.org/10.1016/j.cell.2014.05.010") == "10.1016/j.cell.2014.05.010"


# ===== DOI CLASSIFICATION TESTS =====


class TestDatasetDois:
    """Test dataset DOI classification."""

    def test_zenodo_datasets(self):
        assert classify_doi("10.5281/zenodo.5732995") == DoiType.DATASET
        assert classify_doi("10.5281/zenodo.18025764") == DoiType.DATASET

    def test_figshare_datasets(self):
        assert classify_doi("10.6084/m9.figshare.5725663") == DoiType.DATASET
        assert classify_doi("10.6084/m9.figshare.7848023.v1") == DoiType.DATASET

    def test_mendeley_data(self):
        assert classify_doi("10.17632/dbj46mw6j9.1") == DoiType.DATASET
        assert classify_doi("10.17632/wpfycmb5sv.1") == DoiType.DATASET
        assert classify_doi("10.17632/7w2cdsrt87.1") == DoiType.DATASET

    def test_osf_datasets(self):
        assert classify_doi("10.17605/osf.io/nw5kx") == DoiType.DATASET

    def test_university_repositories(self):
        assert classify_doi("10.5523/bris.356boayld729v2snyncfoltt0w") == DoiType.DATASET
        assert classify_doi("10.5518/880") == DoiType.DATASET
        assert classify_doi("10.4233/uuid:8c624c7a-15c4-41a1-8cc6-7eb8a9b36a86") == DoiType.DATASET
        assert classify_doi("10.22032/dbt.38279") == DoiType.DATASET
        assert classify_doi("10.24355/dbbs.084-202106031104-0") == DoiType.DATASET
        assert classify_doi("10.26153/tsw/62176") == DoiType.DATASET
        assert classify_doi("10.14264/e2cac92") == DoiType.DATASET


class TestPreprintDois:
    """Test preprint DOI classification."""

    def test_biorxiv_date_pattern(self):
        assert classify_doi("10.1101/2020.04.27.062182") == DoiType.PREPRINT
        assert classify_doi("10.1101/2022.02.03.479040") == DoiType.PREPRINT

    def test_biorxiv_short_pattern(self):
        assert classify_doi("10.1101/344564") == DoiType.PREPRINT
        assert classify_doi("10.1101/324855") == DoiType.PREPRINT

    def test_arxiv(self):
        assert classify_doi("10.48550/arxiv.2102.05531") == DoiType.PREPRINT
        assert classify_doi("10.48550/arxiv.2508.02276") == DoiType.PREPRINT

    def test_ssrn(self):
        assert classify_doi("10.2139/ssrn.4052258") == DoiType.PREPRINT
        assert classify_doi("10.2139/ssrn.4102629") == DoiType.PREPRINT

    def test_research_square(self):
        assert classify_doi("10.21203/rs.3.rs-1297929/v1") == DoiType.PREPRINT

    def test_morressier_preprints(self):
        assert classify_doi("10.26226/morressier.5b5199c2b1b87b000ecf126d") == DoiType.PREPRINT

    def test_genome_research_not_preprint(self):
        """10.1101/gr.* is Genome Research journal, not bioRxiv preprint."""
        assert classify_doi("10.1101/gr.279771.124") == DoiType.JOURNAL


class TestSupplementaryDois:
    """Test supplementary material DOI classification."""

    def test_frontiers_supplementary(self):
        assert classify_doi("10.3389/fmolb.2021.732079.s001") == DoiType.SUPPLEMENTARY
        assert classify_doi("10.3389/fmed.2025.1624683.s001") == DoiType.SUPPLEMENTARY

    def test_acs_supplementary(self):
        assert classify_doi("10.1021/acs.jmedchem.5c00836.s001") == DoiType.SUPPLEMENTARY
        assert classify_doi("10.1021/acs.jmedchem.5c00836.s003") == DoiType.SUPPLEMENTARY
        assert classify_doi("10.1021/acs.jmedchem.5c00836.s004") == DoiType.SUPPLEMENTARY

    def test_altex_supplementary(self):
        """ALTEX uses no dot before s1/s2."""
        assert classify_doi("10.14573/altex.1812101s1") == DoiType.SUPPLEMENTARY
        assert classify_doi("10.14573/altex.1812101s2") == DoiType.SUPPLEMENTARY


class TestEditorialDois:
    """Test editorial/commentary DOI classification."""

    def test_f1000_recommendations(self):
        assert classify_doi("10.3410/f.734655916.793555967") == DoiType.EDITORIAL
        assert classify_doi("10.3410/f.725953914.793535742") == DoiType.EDITORIAL

    def test_f1000research(self):
        assert classify_doi("10.7490/f1000research.1113292.1") == DoiType.EDITORIAL
        assert classify_doi("10.7490/f1000research.1117288.1") == DoiType.EDITORIAL

    def test_elife_editorial(self):
        assert classify_doi("10.7554/elife.64047.sa1") == DoiType.EDITORIAL
        assert classify_doi("10.7554/elife.64047.sa2") == DoiType.EDITORIAL
        assert classify_doi("10.7554/elife.34789.025") == DoiType.EDITORIAL


class TestBookChapterDois:
    """Test book chapter DOI classification."""

    def test_springer_book_chapters(self):
        assert classify_doi("10.1007/978-1-0716-0822-7_14") == DoiType.BOOK_CHAPTER
        assert classify_doi("10.1007/978-1-0716-4290-0_6") == DoiType.BOOK_CHAPTER

    def test_elsevier_book_chapters(self):
        assert classify_doi("10.1016/b978-0-12-811718-7.00014-9") == DoiType.BOOK_CHAPTER
        assert classify_doi("10.1016/b978-0-323-85159-6.50367-5") == DoiType.BOOK_CHAPTER

    def test_other_publishers(self):
        assert classify_doi("10.1201/9781315154060-8") == DoiType.BOOK_CHAPTER  # Taylor & Francis
        assert classify_doi("10.1515/9780691223407-008") == DoiType.BOOK_CHAPTER  # De Gruyter
        assert classify_doi("10.4018/978-1-5225-1756-6.ch009") == DoiType.BOOK_CHAPTER  # IGI Global


class TestConferenceAbstractDois:
    """Test conference abstract DOI classification (if implemented)."""

    def test_conference_abstracts(self):
        # These would need to be added based on actual patterns
        # Example: 10.1096/fasebj.2022.36.S1.R4321
        pass


class TestJournalDois:
    """Test journal article DOI classification."""

    def test_nature_journals(self):
        assert classify_doi("10.1038/s41477-018-0328-1") == DoiType.JOURNAL

    def test_cell_press(self):
        assert classify_doi("10.1016/j.cell.2024.11.015") == DoiType.JOURNAL

    def test_plos(self):
        assert classify_doi("10.1371/journal.pcbi.1006333") == DoiType.JOURNAL

    def test_oxford_journals(self):
        assert classify_doi("10.1093/bioinformatics/bty530") == DoiType.JOURNAL

    def test_frontiers_journals(self):
        """Regular Frontiers articles (not supplementary)."""
        assert classify_doi("10.3389/fcell.2023.1260507") == DoiType.JOURNAL


class TestEdgeCases:
    """Test edge cases and ambiguous DOIs."""

    def test_unknown_registrar(self):
        """Unknown registrars should be classified as OTHER."""
        doi1 = classify_doi("10.64898/2026.01.21.700212")
        doi2 = classify_doi("10.71889/5fylantbak.30807980.v1")
        # These could be DATASET or OTHER depending on implementation
        assert doi1 in [DoiType.DATASET, DoiType.OTHER]
        assert doi2 in [DoiType.DATASET, DoiType.OTHER]

    def test_case_insensitivity(self):
        """DOI classification should be case-insensitive."""
        assert classify_doi("10.48550/ARXIV.2102.05531") == DoiType.PREPRINT
        assert classify_doi("10.5281/ZENODO.5732995") == DoiType.DATASET


# ===== IS_RESEARCH_PAPER TESTS =====


def test_is_research_paper_journal():
    assert is_research_paper("10.1038/s41477-018-0328-1") is True
    assert is_research_paper("10.1016/j.cell.2024.11.015") is True


def test_is_research_paper_preprint():
    assert is_research_paper("10.1101/2020.04.27.062182") is True
    assert is_research_paper("10.48550/arxiv.2102.05531") is True


def test_is_research_paper_book_chapter():
    assert is_research_paper("10.1007/978-1-0716-0822-7_14") is True


def test_is_research_paper_dataset():
    assert is_research_paper("10.5281/zenodo.5732995") is False


def test_is_research_paper_supplementary():
    assert is_research_paper("10.3389/fmolb.2021.732079.s001") is False


def test_is_research_paper_editorial():
    assert is_research_paper("10.3410/f.734655916.793555967") is False


# ===== DEDUPLICATION TESTS =====


class TestPreprintDeduplication:
    """Test deduplication of preprint/published pairs."""

    def test_remove_preprint_when_published_exists(self):
        papers = [
            {"doi": "10.1101/2022.02.03.479040", "title": "Multiscale model of primary motor cortex circuits"},
            {"doi": "10.1016/j.celrep.2023.112574", "title": "Multiscale model of primary motor cortex circuits predicts in vivo cell-type-specific dynamics"},
        ]
        result = deduplicate_preprints(papers)
        assert len(result) == 1
        assert result[0]["doi"] == "10.1016/j.celrep.2023.112574"

    def test_keep_preprint_when_no_published(self):
        papers = [
            {"doi": "10.1101/2020.04.27.062182", "title": "Some preprint study"},
        ]
        result = deduplicate_preprints(papers)
        assert len(result) == 1
        assert result[0]["doi"] == "10.1101/2020.04.27.062182"

    def test_multiple_preprint_pairs(self):
        papers = [
            {"doi": "10.1101/2020.01.01.100001", "title": "Study A preprint"},
            {"doi": "10.1038/s41586-020-12345-6", "title": "Study A published"},
            {"doi": "10.1101/2020.02.02.200002", "title": "Study B preprint"},
            {"doi": "10.1016/j.cell.2020.03.001", "title": "Study B published"},
            {"doi": "10.1101/2020.03.03.300003", "title": "Study C preprint only"},
        ]
        result = deduplicate_preprints(papers)
        assert len(result) == 3
        dois = [p["doi"] for p in result]
        assert "10.1038/s41586-020-12345-6" in dois
        assert "10.1016/j.cell.2020.03.001" in dois
        assert "10.1101/2020.03.03.300003" in dois
        assert "10.1101/2020.01.01.100001" not in dois
        assert "10.1101/2020.02.02.200002" not in dois

    def test_arxiv_deduplication(self):
        papers = [
            {"doi": "10.48550/arxiv.2102.05531", "title": "Machine learning study"},
            {"doi": "10.1038/s41586-2021-12345-6", "title": "Machine learning study"},
        ]
        result = deduplicate_preprints(papers)
        assert len(result) == 1
        assert result[0]["doi"] == "10.1038/s41586-2021-12345-6"

    def test_title_matching_threshold(self):
        """Test that similar but not identical titles are matched."""
        papers = [
            {"doi": "10.1101/2022.02.03.479040", "title": "Multiscale model of motor cortex"},
            {"doi": "10.1016/j.celrep.2023.112574", "title": "Multiscale model of primary motor cortex circuits"},
        ]
        result = deduplicate_preprints(papers)
        # Should match because titles are similar enough
        assert len(result) == 1
        assert result[0]["doi"] == "10.1016/j.celrep.2023.112574"

    def test_no_title_field(self):
        """Test handling papers without title field."""
        papers = [
            {"doi": "10.1101/2020.01.01.100001"},
            {"doi": "10.1038/s41586-020-12345-6"},
        ]
        result = deduplicate_preprints(papers)
        # Without titles, can't match, should keep both
        assert len(result) == 2


# ===== CLEAN_PAPERS TESTS =====


class TestCleanPapers:
    """Test the combined clean_papers function."""

    def test_full_cleaning_pipeline(self):
        """Test with a realistic mixed dataset."""
        papers = [
            # Journal articles (keep)
            {"doi": "10.1038/s41477-018-0328-1", "title": "Nature Plants article"},
            {"doi": "10.1016/j.cell.2024.11.015", "title": "Cell article"},
            {"doi": "10.1371/journal.pcbi.1006333", "title": "PLOS article"},
            # Preprint + published pair (remove preprint)
            {"doi": "10.1101/2022.02.03.479040", "title": "Motor cortex study"},
            {"doi": "10.1016/j.celrep.2023.112574", "title": "Motor cortex study published"},
            # Preprint only (keep)
            {"doi": "10.1101/2020.04.27.062182", "title": "Standalone preprint"},
            # Dataset (remove)
            {"doi": "10.5281/zenodo.5732995", "title": "Zenodo dataset"},
            {"doi": "10.6084/m9.figshare.5725663", "title": "Figshare data"},
            # Supplementary (remove)
            {"doi": "10.3389/fmolb.2021.732079.s001", "title": "Supplementary file"},
            # Editorial (remove)
            {"doi": "10.3410/f.734655916.793555967", "title": "F1000 recommendation"},
            # Book chapter (keep)
            {"doi": "10.1007/978-1-0716-0822-7_14", "title": "Springer chapter"},
        ]

        cleaned, stats = clean_papers(papers, remove_non_papers=True, dedupe_preprints=True)

        # Should keep: 3 journals + 1 standalone preprint + 1 published version + 1 book chapter = 6
        assert len(cleaned) == 6

        # Verify stats
        assert stats["total_input"] == 11
        assert stats["removed_datasets"] == 2
        assert stats["removed_supplementary"] == 1
        assert stats["removed_editorial"] == 1
        assert stats["removed_preprint_duplicates"] == 1
        assert stats["final_count"] == 6

        # Verify DOIs in cleaned list
        dois = [p["doi"] for p in cleaned]
        assert "10.1038/s41477-018-0328-1" in dois
        assert "10.1016/j.cell.2024.11.015" in dois
        assert "10.1371/journal.pcbi.1006333" in dois
        assert "10.1016/j.celrep.2023.112574" in dois  # published version
        assert "10.1101/2020.04.27.062182" in dois  # standalone preprint
        assert "10.1007/978-1-0716-0822-7_14" in dois  # book chapter
        assert "10.1101/2022.02.03.479040" not in dois  # preprint duplicate
        assert "10.5281/zenodo.5732995" not in dois  # dataset

    def test_skip_deduplication(self):
        """Test with dedupe_preprints=False."""
        papers = [
            {"doi": "10.1101/2022.02.03.479040", "title": "Motor cortex study"},
            {"doi": "10.1016/j.celrep.2023.112574", "title": "Motor cortex study published"},
        ]

        cleaned, stats = clean_papers(papers, remove_non_papers=True, dedupe_preprints=False)

        # Should keep both
        assert len(cleaned) == 2
        assert stats["removed_preprint_duplicates"] == 0

    def test_skip_non_paper_removal(self):
        """Test with remove_non_papers=False."""
        papers = [
            {"doi": "10.1038/s41477-018-0328-1", "title": "Journal article"},
            {"doi": "10.5281/zenodo.5732995", "title": "Dataset"},
            {"doi": "10.3389/fmolb.2021.732079.s001", "title": "Supplementary"},
        ]

        cleaned, stats = clean_papers(papers, remove_non_papers=False, dedupe_preprints=True)

        # Should keep all
        assert len(cleaned) == 3
        assert stats["removed_datasets"] == 0
        assert stats["removed_supplementary"] == 0

    def test_empty_input(self):
        """Test with empty list."""
        cleaned, stats = clean_papers([], remove_non_papers=True, dedupe_preprints=True)

        assert len(cleaned) == 0
        assert stats["total_input"] == 0
        assert stats["final_count"] == 0

    def test_all_datasets(self):
        """Test with only datasets."""
        papers = [
            {"doi": "10.5281/zenodo.5732995", "title": "Dataset 1"},
            {"doi": "10.6084/m9.figshare.5725663", "title": "Dataset 2"},
        ]

        cleaned, stats = clean_papers(papers, remove_non_papers=True, dedupe_preprints=True)

        assert len(cleaned) == 0
        assert stats["removed_datasets"] == 2
        assert stats["final_count"] == 0
