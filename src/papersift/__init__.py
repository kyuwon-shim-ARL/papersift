"""PaperSift: Entity-based paper clustering for Claude Code."""

from papersift.entity_layer import EntityLayerBuilder, ImprovedEntityExtractor
from papersift.validator import ClusterValidator, ValidationReport
from papersift.doi import normalize_doi, classify_doi, is_research_paper, clean_papers, DoiType

__version__ = "0.3.0"
__all__ = [
    "EntityLayerBuilder",
    "ImprovedEntityExtractor",
    "ClusterValidator",
    "ValidationReport",
    "normalize_doi",
    "classify_doi",
    "is_research_paper",
    "clean_papers",
    "DoiType",
]

try:
    from papersift.enrich import OpenAlexEnricher
    __all__.append("OpenAlexEnricher")
except ImportError:
    pass  # pyalex not installed

try:
    from papersift.embedding import (
        embed_papers,
        build_entity_matrix,
        compute_embedding,
        sub_cluster,
        extract_paper_entities,
    )
    __all__.extend([
        "embed_papers",
        "build_entity_matrix",
        "compute_embedding",
        "sub_cluster",
        "extract_paper_entities",
    ])
except ImportError:
    pass  # Should not happen since numpy/sklearn are core deps

try:
    from papersift.pipeline import (
        PaperDiscovery,
        PaperFetcher,
        ContentResult,
        PaperExtractor,
        ExtractionResult,
        PaperStore,
    )
    __all__.extend([
        "PaperDiscovery",
        "PaperFetcher",
        "ContentResult",
        "PaperExtractor",
        "ExtractionResult",
        "PaperStore",
    ])
except ImportError:
    pass  # pipeline dependencies not installed

try:
    from papersift.abstract import AbstractFetcher
    from papersift.research import ResearchPipeline, ResearchOutput, PreparedData
    from papersift.extract import build_batch_prompts, parse_llm_response, merge_extractions
    __all__.extend([
        "AbstractFetcher",
        "ResearchPipeline",
        "ResearchOutput",
        "PreparedData",
        "build_batch_prompts",
        "parse_llm_response",
        "merge_extractions",
    ])
except ImportError:
    pass
