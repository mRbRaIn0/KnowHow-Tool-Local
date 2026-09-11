from __future__ import annotations

import shutil
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.backups import create_backup
from backend.config import Profile
from backend.database import Database


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path.cwd() / ".test-runtime" / "backup"
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

    def test_backup_contains_vault_profile_and_consistent_database(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        (vault / "Wissen.md").write_text("# Wissen\n", encoding="utf-8")
        profile = Profile(id="test", name="Test")

        with patch("backend.config.PROFILE_DATA_DIR", self.temp / "profiles"), \
             patch("backend.backups.DATA_DIR", self.temp / "data"):
            database = Database(profile.db_path)
            try:
                chat = database.create_chat("Gespräch")
                database.add_message(chat["id"], "user", "Hallo")
                result = create_backup(profile, vault, database)
            finally:
                database.close()

            backup = self.temp / "data" / "backups" / "test" / result["name"]
            with zipfile.ZipFile(backup) as archive:
                names = set(archive.namelist())
                self.assertIn("vault/Wissen.md", names)
                self.assertIn("app/app.db", names)
                self.assertIn("app/profile.json", names)
                self.assertIn("manifest.json", names)


if __name__ == "__main__":
    unittest.main()
