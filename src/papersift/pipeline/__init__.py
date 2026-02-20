"""Paper acquisition pipeline - search, fetch, extract, store."""

try:
    from papersift.pipeline.discovery import PaperDiscovery
    from papersift.pipeline.fetcher import PaperFetcher, ContentResult
    from papersift.pipeline.extractor import PaperExtractor, ExtractionResult
    from papersift.pipeline.store import PaperStore

    __all__ = [
        "PaperDiscovery",
        "PaperFetcher",
        "ContentResult",
        "PaperExtractor",
        "ExtractionResult",
        "PaperStore",
    ]
except ImportError:
    # Pipeline dependencies not installed
    pass
