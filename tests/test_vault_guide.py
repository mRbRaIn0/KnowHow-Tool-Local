from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from backend.vault_guide import GUIDE_PATH, ensure_vault_guide


class VaultGuideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path.cwd() / ".test-runtime" / "vault-guide"
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

    def test_creates_main_page_with_rules_and_real_vault_links(self) -> None:
        folder = self.temp / "01 Wissen" / "Docker"
        folder.mkdir(parents=True)
        (folder / "Grundlagen.md").write_text("# Grundlagen\n", encoding="utf-8")
        (folder / "Quelle.pdf").write_bytes(b"pdf")

        result = ensure_vault_guide(self.temp)
        content = (self.temp / GUIDE_PATH).read_text(encoding="utf-8")

        self.assertTrue(result["created"])
        self.assertIn("- Emojis: Nein", content)
        self.assertIn("`01 Wissen/Docker/`", content)
        self.assertIn("[[01 Wissen/Docker/Grundlagen|Grundlagen]]", content)
        self.assertIn("[[01 Wissen/Docker/Quelle.pdf|Quelle.pdf]]", content)

    def test_refresh_preserves_user_rules_outside_managed_index(self) -> None:
        ensure_vault_guide(self.temp)
        guide = self.temp / GUIDE_PATH
        content = guide.read_text(encoding="utf-8").replace("Emojis: Nein", "Emojis: Ja")
        guide.write_text(content, encoding="utf-8")
        (self.temp / "Neues Wissen").mkdir()
        (self.temp / "Neues Wissen" / "Thema.md").write_text("# Thema\n", encoding="utf-8")

        result = ensure_vault_guide(self.temp)
        refreshed = guide.read_text(encoding="utf-8")

        self.assertTrue(result["updated"])
        self.assertIn("Emojis: Ja", refreshed)
        self.assertIn("[[Neues Wissen/Thema|Thema]]", refreshed)

    def test_existing_custom_main_page_without_markers_is_never_rewritten(self) -> None:
        custom = "# Meine Hauptseite\n\n- Emojis: Ja\n- Eigene Ordnung bleibt.\n"
        (self.temp / GUIDE_PATH).write_text(custom, encoding="utf-8")
        (self.temp / "Ordner").mkdir()

        result = ensure_vault_guide(self.temp)

        self.assertFalse(result["created"])
        self.assertFalse(result["updated"])
        self.assertEqual((self.temp / GUIDE_PATH).read_text(encoding="utf-8"), custom)


if __name__ == "__main__":
    unittest.main()
