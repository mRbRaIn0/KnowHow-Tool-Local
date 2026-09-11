import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import config


class ApplicationRootTests(unittest.TestCase):
    def test_in_project_exe_reuses_existing_project_data(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            project = Path(folder)
            (project / "dist").mkdir()
            (project / "data").mkdir()
            (project / "data" / "config.json").write_text("{}", encoding="utf-8")

            with patch.object(config.sys, "frozen", True, create=True), \
                    patch.object(config.sys, "executable", str(project / "dist" / "Lokale-Wissens-KI.exe")):
                self.assertEqual(config._application_root(), project.resolve())

    def test_portable_exe_keeps_data_beside_itself(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            release = Path(folder) / "release"
            release.mkdir()

            with patch.object(config.sys, "frozen", True, create=True), \
                    patch.object(config.sys, "executable", str(release / "Lokale-Wissens-KI.exe")):
                self.assertEqual(config._application_root(), release.resolve())


class ConfigUpgradeTests(unittest.TestCase):
    def test_old_config_keeps_vault_and_fills_new_ai_defaults(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            path = root / "config.json"
            path.write_text(json.dumps({
                "version": 1,
                "active_profile": "privat",
                "server": {"host": "127.0.0.1", "port": 5000},
                "profiles": [{
                    "id": "privat",
                    "name": "Privat",
                    "vault": {"path": str(root / "Vault")},
                    "ollama": {"chat_model": "qwen3.5:9b"},
                }],
            }), encoding="utf-8")

            with patch.object(config, "PROFILE_DATA_DIR", root / "profiles"):
                store = config.ConfigStore(path)
                loaded = store.load()

            self.assertEqual(loaded.version, 2)
            self.assertEqual(loaded.server.port, 0)
            self.assertEqual(loaded.profiles[0].vault.path, str(root / "Vault"))
            self.assertEqual(loaded.profiles[0].ollama.chat_model, "qwen3.5:9b")
            self.assertTrue(loaded.profiles[0].ai.thinking)
            self.assertTrue((root / config.DATA_HINT_NAME).is_file())

    def test_existing_profile_database_is_reused_after_config_reload(self) -> None:
        from backend.database import Database

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            profiles = root / "profiles"
            db_path = profiles / "privat" / "app.db"
            with patch.object(config, "PROFILE_DATA_DIR", profiles):
                database = Database(db_path)
                try:
                    chat = database.create_chat("Bleibt erhalten")
                    database.add_message(chat["id"], "user", "Hallo")
                finally:
                    database.close()

                path = root / "config.json"
                path.write_text(json.dumps({
                    "version": 2,
                    "active_profile": "privat",
                    "profiles": [{"id": "privat", "name": "Privat"}],
                }), encoding="utf-8")
                store = config.ConfigStore(path)
                profile = store.load().profiles[0]
                self.assertEqual(profile.db_path, db_path.resolve())

                again = Database(profile.db_path)
                try:
                    chats = again.list_chats()
                    self.assertEqual([item["title"] for item in chats], ["Bleibt erhalten"])
                    self.assertEqual(again.list_messages(chats[0]["id"])[0]["content"], "Hallo")
                finally:
                    again.close()


if __name__ == "__main__":
    unittest.main()
