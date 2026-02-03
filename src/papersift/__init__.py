"""PaperSift: Entity-based paper clustering for Claude Code."""

from papersift.entity_layer import EntityLayerBuilder, ImprovedEntityExtractor
from papersift.validator import ClusterValidator, ValidationReport

__version__ = "0.1.0"
__all__ = [
    "EntityLayerBuilder",
    "ImprovedEntityExtractor",
    "ClusterValidator",
    "ValidationReport",
]

try:
    from papersift.enrich import OpenAlexEnricher
    __all__.append("OpenAlexEnricher")
except ImportError:
    pass  # pyalex not installed
