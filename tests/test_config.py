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


if __name__ == "__main__":
    unittest.main()
