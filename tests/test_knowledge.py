from __future__ import annotations

import asyncio
import shutil
import unittest
from pathlib import Path

from backend.database import Database
from backend.knowledge import hybrid_search, sync_index


class KnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path.cwd() / ".test-runtime" / "knowledge"
        if self.temp.exists():
            shutil.rmtree(self.temp)
        self.temp.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.temp.exists():
            shutil.rmtree(self.temp)
        try:
            self.temp.parent.rmdir()
        except OSError:
            pass

    def test_local_index_and_lexical_fallback(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        (vault / "Docker.md").write_text(
            "# Docker Volumes\n\nVolumes speichern Containerdaten dauerhaft.",
            encoding="utf-8",
        )
        database = Database(self.temp / "app.db")
        try:
            status = asyncio.run(sync_index(vault, database, None, ""))
            result = asyncio.run(
                hybrid_search(vault, database, "Docker Volumes", None, "", 5)
            )
        finally:
            database.close()

        self.assertEqual(status["files"], 1)
        self.assertEqual(result["results"][0]["path"], "Docker.md")
        self.assertIn("Containerdaten", result["results"][0]["content"])


if __name__ == "__main__":
    unittest.main()
