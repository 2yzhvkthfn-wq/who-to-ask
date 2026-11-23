import json
from typing import Dict, List

import yaml

from config.settings import PROJECT_ROOT, settings
from utils.logging import logger

# The JSON files of the data folder. Each one fills the MongoDB collection of the same name: people.json -> people
JSON_COLLECTIONS = ["teams", "systems", "people", "hr_records", "tickets"]


class SeedFiles:
    """Reads the fake company files of the data folder. They are the seed source: what the seed script copies to MongoDB."""

    def __init__(self):
        # The data folder, from the settings
        self.folder = PROJECT_ROOT / settings.DATA_DIR

    def read(self) -> Dict[str, List[Dict]]:
        """Return every record of every file, by collection name. Each list keeps the order of its file."""
        # 1) One JSON file per collection
        collections = {name: self._read_json(f"{name}.json") for name in JSON_COLLECTIONS}
        # 2) The pages: one Markdown file per page
        collections["pages"] = self._read_pages()
        return collections

    def _read_json(self, file_name: str) -> List[Dict]:
        """Read one JSON file from the data folder."""
        try:
            return json.loads((self.folder / file_name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.error(f"Could not read {file_name}: {e}")
            raise

    def _read_pages(self) -> List[Dict]:
        """Read every Markdown file in the pages folder, in file-name order."""
        pages = []
        for path in sorted((self.folder / "pages").glob("*.md")):
            try:
                pages.append(self._parse_page(path.name, path.read_text(encoding="utf-8")))
            except (OSError, ValueError, yaml.YAMLError) as e:
                logger.error(f"Could not read the page {path.name}: {e}")
                raise
        return pages

    def _parse_page(self, file_name: str, text: str) -> Dict:
        """Split one file into its header (between the two --- lines) and its body."""
        if not text.startswith("---\n"):
            raise ValueError("the file must start with a --- line")
        header_text, separator, body = text[4:].partition("\n---\n")
        if not separator:
            raise ValueError("the header has no closing --- line")

        # BaseLoader keeps every value as text, so a date stays "2026-10-12"
        header = yaml.load(header_text, Loader=yaml.BaseLoader)
        if not isinstance(header, dict):
            raise ValueError("the header must be made of name: value lines")
        # A page record: its header fields, plus "body" (the text) and "file" (the name of its file)
        return {**header, "body": body.strip(), "file": file_name}
