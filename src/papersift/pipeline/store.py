"""Hierarchical paper storage with L0-L3 layers."""

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


class PaperStore:
    """Paper storage with layered data and collection management."""

    LAYER_FILES = {
        "L0": "metadata.json",
        "L1": "abstract.json",
        "L2": "sections.json",
        "L3": "analysis.json",
    }

    CONTENT_FILES = {
        "fulltext": "content/fulltext.md",
        "abstract": "content/raw_abstract.txt",
        "pdf": "content/source.pdf",
        "grobid_tei": "content/grobid.tei.xml",
        "europe_pmc_xml": "content/europe_pmc.xml",
    }

    def __init__(self, base_dir: str = "data/papers"):
        """Initialize store with base directory.

        Args:
            base_dir: Base directory for paper storage
        """
        self.base_dir = Path(base_dir)
        self.by_doi_dir = self.base_dir / "by-doi"
        self.by_collection_dir = self.base_dir / "by-collection"
        self.index_path = self.base_dir / "index.json"

        # Create directories
        self.by_doi_dir.mkdir(parents=True, exist_ok=True)
        self.by_collection_dir.mkdir(parents=True, exist_ok=True)

        # Load or create index
        self._index = self._load_index()

    def _load_index(self) -> dict:
        """Load index.json or create empty index."""
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "version": "1.0",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "paper_count": 0,
            "papers": {},
        }

    def _save_index(self):
        """Save index with atomic write (temp file + rename)."""
        self._index["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        self._index["paper_count"] = len(self._index["papers"])

        # Atomic write
        fd, tmp_path = tempfile.mkstemp(
            dir=self.base_dir, prefix=".index_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.index_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def doi_to_dirname(doi: str) -> str:
        """Convert DOI to safe directory name.

        Args:
            doi: DOI string (with or without https://doi.org/ prefix)

        Returns:
            Safe directory name
        """
        # Remove URL prefix
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

        # Replace / with __
        safe = doi.replace("/", "__")

        # Replace other special chars with hex
        safe = re.sub(
            r"[^a-zA-Z0-9._\-]",
            lambda m: f"_{ord(m.group()):02x}_",
            safe,
        )

        return safe

    def get_paper_dir(self, doi: str) -> Path:
        """Get full path to paper directory.

        Args:
            doi: Paper DOI

        Returns:
            Path to paper directory
        """
        return self.by_doi_dir / self.doi_to_dirname(doi)

    def save_layer(self, doi: str, layer: str, data: dict) -> Path:
        """Save layer data for a paper.

        Args:
            doi: Paper DOI
            layer: Layer name (L0, L1, L2, L3)
            data: Dict to save as JSON

        Returns:
            Path to saved file
        """
        if layer not in self.LAYER_FILES:
            raise ValueError(f"Invalid layer: {layer}. Must be one of {list(self.LAYER_FILES.keys())}")

        paper_dir = self.get_paper_dir(doi)
        paper_dir.mkdir(parents=True, exist_ok=True)

        file_path = paper_dir / self.LAYER_FILES[layer]

        # Atomic write
        fd, tmp_path = tempfile.mkstemp(
            dir=paper_dir, prefix=f".{layer}_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, file_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        # Update index
        self._ensure_paper_in_index(doi, data if layer == "L0" else None)
        self._index["papers"][doi]["layers"][layer] = True
        self._save_index()

        return file_path

    def load_layer(self, doi: str, layer: str) -> Optional[dict]:
        """Load layer data for a paper.

        Args:
            doi: Paper DOI
            layer: Layer name

        Returns:
            Dict data or None if not exists
        """
        if layer not in self.LAYER_FILES:
            raise ValueError(f"Invalid layer: {layer}")

        file_path = self.get_paper_dir(doi) / self.LAYER_FILES[layer]

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def has_layer(self, doi: str, layer: str) -> bool:
        """Check if paper has a specific layer.

        Args:
            doi: Paper DOI
            layer: Layer name

        Returns:
            True if layer exists
        """
        if layer not in self.LAYER_FILES:
            raise ValueError(f"Invalid layer: {layer}")

        file_path = self.get_paper_dir(doi) / self.LAYER_FILES[layer]
        return file_path.exists()

    def save_content(
        self, doi: str, content_type: str, data: Union[str, bytes]
    ) -> Path:
        """Save content file (PDF, XML, etc.).

        Args:
            doi: Paper DOI
            content_type: Type (fulltext, abstract, pdf, grobid_tei, europe_pmc_xml)
            data: String or bytes to save

        Returns:
            Path to saved file
        """
        if content_type not in self.CONTENT_FILES:
            raise ValueError(f"Invalid content_type: {content_type}")

        paper_dir = self.get_paper_dir(doi)
        content_dir = paper_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=True)

        file_path = paper_dir / self.CONTENT_FILES[content_type]

        mode = "wb" if isinstance(data, bytes) else "w"
        encoding = None if isinstance(data, bytes) else "utf-8"

        with open(file_path, mode, encoding=encoding) as f:
            f.write(data)

        # Update index
        self._ensure_paper_in_index(doi)
        self._index["papers"][doi]["content_available"] = True
        self._save_index()

        return file_path

    def load_content(
        self, doi: str, content_type: str, binary: bool = False
    ) -> Optional[Union[str, bytes]]:
        """Load content file.

        Args:
            doi: Paper DOI
            content_type: Content type
            binary: Read as binary

        Returns:
            Content string/bytes or None
        """
        if content_type not in self.CONTENT_FILES:
            raise ValueError(f"Invalid content_type: {content_type}")

        file_path = self.get_paper_dir(doi) / self.CONTENT_FILES[content_type]

        if not file_path.exists():
            return None

        mode = "rb" if binary else "r"
        encoding = None if binary else "utf-8"

        with open(file_path, mode, encoding=encoding) as f:
            return f.read()

    def _ensure_paper_in_index(self, doi: str, metadata: Optional[dict] = None):
        """Ensure paper exists in index, create entry if needed."""
        if doi not in self._index["papers"]:
            self._index["papers"][doi] = {
                "paper_id": self.doi_to_dirname(doi),
                "openalex_id": metadata.get("openalex_id", "") if metadata else "",
                "title": metadata.get("title", "") if metadata else "",
                "year": metadata.get("publication_year") if metadata else None,
                "layers": {"L0": False, "L1": False, "L2": False, "L3": False},
                "oa_status": metadata.get("oa_status") if metadata else None,
                "content_source": None,
                "content_available": False,
                "extraction_method": None,
                "collections": [],
                "added_date": datetime.now().strftime("%Y-%m-%d"),
            }
        elif metadata:
            # Update with metadata
            entry = self._index["papers"][doi]
            entry["openalex_id"] = metadata.get("openalex_id", entry.get("openalex_id", ""))
            entry["title"] = metadata.get("title", entry.get("title", ""))
            entry["year"] = metadata.get("publication_year", entry.get("year"))
            entry["oa_status"] = metadata.get("oa_status", entry.get("oa_status"))

    def update_paper_metadata(
        self,
        doi: str,
        content_source: Optional[str] = None,
        extraction_method: Optional[str] = None,
    ):
        """Update paper metadata in index.

        Args:
            doi: Paper DOI
            content_source: Source of content (europe_pmc, unpaywall, etc.)
            extraction_method: Extraction method used
        """
        self._ensure_paper_in_index(doi)

        if content_source:
            self._index["papers"][doi]["content_source"] = content_source
        if extraction_method:
            self._index["papers"][doi]["extraction_method"] = extraction_method

        self._save_index()

    def list_papers(self, filters: Optional[dict] = None) -> list[dict]:
        """List papers with optional filters.

        Args:
            filters: Optional filters:
                - year_min: Minimum publication year
                - year_max: Maximum publication year
                - oa_only: Only OA papers
                - has_layer: Papers with specific layer
                - collection: Papers in specific collection

        Returns:
            List of paper metadata dicts
        """
        results = []

        for doi, paper in self._index["papers"].items():
            # Apply filters
            if filters:
                if "year_min" in filters and paper.get("year"):
                    if paper["year"] < filters["year_min"]:
                        continue
                if "year_max" in filters and paper.get("year"):
                    if paper["year"] > filters["year_max"]:
                        continue
                if filters.get("oa_only") and paper.get("oa_status") not in ["gold", "green", "hybrid", "bronze"]:
                    continue
                if "has_layer" in filters:
                    if not paper["layers"].get(filters["has_layer"]):
                        continue
                if "collection" in filters:
                    if filters["collection"] not in paper.get("collections", []):
                        continue

            results.append({"doi": doi, **paper})

        return results

    def create_collection(self, name: str, dois: list[str]) -> Path:
        """Create a collection of papers.

        Args:
            name: Collection name
            dois: List of DOIs

        Returns:
            Path to collection file
        """
        collection_dir = self.by_collection_dir / name
        collection_dir.mkdir(parents=True, exist_ok=True)

        collection_file = collection_dir / "collection.json"

        collection_data = {
            "name": name,
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "paper_count": len(dois),
            "dois": dois,
        }

        with open(collection_file, "w", encoding="utf-8") as f:
            json.dump(collection_data, f, indent=2)

        # Update papers' collection membership
        for doi in dois:
            if doi in self._index["papers"]:
                if name not in self._index["papers"][doi]["collections"]:
                    self._index["papers"][doi]["collections"].append(name)

        self._save_index()

        return collection_file

    def get_collection(self, name: str) -> Optional[list[str]]:
        """Get DOIs in a collection.

        Args:
            name: Collection name

        Returns:
            List of DOIs or None if not exists
        """
        collection_file = self.by_collection_dir / name / "collection.json"

        if not collection_file.exists():
            return None

        with open(collection_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("dois", [])

    def list_collections(self) -> list[str]:
        """List all collection names.

        Returns:
            List of collection names
        """
        collections = []
        for item in self.by_collection_dir.iterdir():
            if item.is_dir() and (item / "collection.json").exists():
                collections.append(item.name)
        return sorted(collections)

    def add_to_collection(self, name: str, dois: list[str]):
        """Add papers to existing collection.

        Args:
            name: Collection name
            dois: DOIs to add
        """
        existing = self.get_collection(name)
        if existing is None:
            self.create_collection(name, dois)
        else:
            new_dois = list(set(existing + dois))
            self.create_collection(name, new_dois)

    def get_stats(self) -> dict:
        """Get storage statistics.

        Returns:
            Stats dict with counts by layer, content availability, etc.
        """
        stats = {
            "total_papers": len(self._index["papers"]),
            "by_layer": {"L0": 0, "L1": 0, "L2": 0, "L3": 0},
            "content_available": 0,
            "by_extraction_method": {},
            "by_oa_status": {},
            "collections": len(self.list_collections()),
        }

        for paper in self._index["papers"].values():
            for layer in ["L0", "L1", "L2", "L3"]:
                if paper["layers"].get(layer):
                    stats["by_layer"][layer] += 1

            if paper.get("content_available"):
                stats["content_available"] += 1

            method = paper.get("extraction_method")
            if method:
                stats["by_extraction_method"][method] = stats["by_extraction_method"].get(method, 0) + 1

            oa = paper.get("oa_status")
            if oa:
                stats["by_oa_status"][oa] = stats["by_oa_status"].get(oa, 0) + 1

        return stats

    def generate_readme(self, doi: str) -> Path:
        """Generate README.md for a paper.

        Args:
            doi: Paper DOI

        Returns:
            Path to README
        """
        paper_dir = self.get_paper_dir(doi)
        metadata = self.load_layer(doi, "L0")

        if not metadata:
            raise ValueError(f"No L0 metadata for {doi}")

        readme_content = f"""# {metadata.get('title', 'Unknown')}

**DOI**: [{doi}](https://doi.org/{doi})
**Year**: {metadata.get('publication_year', 'Unknown')}
**Journal**: {metadata.get('journal', 'Unknown')}
**Citations**: {metadata.get('cited_by_count', 0)}

## OpenAlex
[View on OpenAlex]({metadata.get('openalex_id', '')})

## Available Layers
"""
        for layer in ["L0", "L1", "L2", "L3"]:
            status = "+" if self.has_layer(doi, layer) else "-"
            readme_content += f"- {layer}: {status}\n"

        readme_path = paper_dir / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

        return readme_path

    def export_papers_json(self, collection: str = None) -> list[dict]:
        """Export papers as flat JSON array for papersift clustering.

        Args:
            collection: Optional collection name to filter by

        Returns:
            List of paper dicts with doi, title, and available fields
        """
        if collection:
            dois = self.get_collection(collection)
            if not dois:
                return []
        else:
            dois = list(self._index["papers"].keys())

        papers = []
        for doi in dois:
            metadata = self.load_layer(doi, "L0")
            if metadata:
                papers.append(metadata)
        return papers
