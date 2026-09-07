from __future__ import annotations

import asyncio
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import attachments
from backend.tools import ToolRunner
from backend.vault_guide import ensure_vault_guide
from backend.workflow import analyse_request


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path.cwd() / ".test-runtime" / "workflow"
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

    def test_explanation_is_not_mistaken_for_write_request(self) -> None:
        result = analyse_request("Wie kann ich eine Notiz erstellen?", ["quelle.pdf"])
        self.assertFalse(result.actionable)

    def test_note_request_with_attachment_requires_copy_and_link(self) -> None:
        result = analyse_request(
            "Erstelle aus dieser Datei eine verständliche Notiz.", ["quelle.pdf"]
        )
        self.assertTrue(result.note_write)
        self.assertTrue(result.archive_attachments)

    def test_explicit_restructure_enables_full_edit(self) -> None:
        result = analyse_request("Ich möchte eine andere Struktur für die Notiz.")
        self.assertTrue(result.requires_edit)
        self.assertTrue(result.allow_full_rewrite)

    def test_global_edit_keeps_scope_from_previous_user_message(self) -> None:
        result = analyse_request(
            "Entferne alle Emojis und ersetze alle relativen Links durch korrekte WikiLinks.",
            context_messages=["Von allen Dateien"],
        )
        self.assertTrue(result.requires_edit)
        self.assertTrue(result.requires_batch_edit)
        self.assertEqual(
            result.batch_edit_operations,
            ("remove_emojis", "fix_relative_links"),
        )

    def test_colloquial_global_task_is_not_reduced_to_single_notes(self) -> None:
        result = analyse_request(
            "1. Entferne die Emojis aller mds 2. Verbessere alle Links, dass diese "
            "auch richtig funktionieren - zwischendrin und auch von den PDFs"
        )
        self.assertTrue(result.requires_batch_edit)
        self.assertEqual(
            result.batch_edit_operations,
            ("remove_emojis", "fix_relative_links"),
        )

    def test_scope_followup_reuses_previous_explicit_edit(self) -> None:
        result = analyse_request(
            "Von allen Dateien",
            context_messages=[
                "Entferne alle Emojs und repariere die relativen Verlinkungen."
            ],
        )
        self.assertTrue(result.requires_batch_edit)

    def test_single_note_remove_request_does_not_enable_batch(self) -> None:
        result = analyse_request("Entferne die Emojis aus dieser Notiz.")
        self.assertTrue(result.requires_edit)
        self.assertFalse(result.requires_batch_edit)

    def test_file_subfolder_request_is_an_executable_vault_action(self) -> None:
        result = analyse_request(
            "Mache immer einen Unterordner mit Dateien, also lasse die PDFs nicht "
            "auf gleicher Ebene wie MD."
        )
        self.assertTrue(result.actionable)
        self.assertTrue(result.organize_vault_files)
        self.assertIn("dateien_in_unterordner_verschieben", result.contract())

    def test_targeted_edit_preserves_unrelated_content(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        note = vault / "Docker.md"
        note.write_text(
            "# Docker\n\nEinleitung bleibt.\n\n## Sicherheit\n\nAlte Aussage.\n\n## Links\n\n[[Linux]]\n",
            encoding="utf-8",
        )
        runner = ToolRunner(vault, allow_edit=True)
        runner._notiz_lesen("Docker.md")
        result = runner._notiz_bearbeiten(
            "Docker.md", "text_ersetzen", "Korrigierte Aussage mit Quelle [[Quelle]].",
            alter_text="Alte Aussage.", grund="Explizite Korrektur",
        )

        content = note.read_text(encoding="utf-8")
        self.assertEqual(result["bearbeitet"], "Docker.md")
        self.assertIn("Einleitung bleibt.", content)
        self.assertIn("[[Linux]]", content)
        self.assertNotIn("Alte Aussage.", content)

    def test_edit_without_explicit_permission_is_rejected(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        (vault / "Notiz.md").write_text("# Notiz\n\nOriginal.\n", encoding="utf-8")
        runner = ToolRunner(vault)
        runner._notiz_lesen("Notiz.md")
        result = runner._notiz_bearbeiten(
            "Notiz.md", "text_ersetzen", "Neu.", alter_text="Original."
        )
        self.assertIn("fehler", result)
        self.assertIn("Original.", (vault / "Notiz.md").read_text(encoding="utf-8"))

    def test_full_restructure_preserves_frontmatter_and_facts(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        note = vault / "Server.md"
        note.write_text(
            "---\ntags: [it]\nstatus: geprüft\n---\n\n# Server\n\n"
            "Firewall schützt Netzwerkdienste. Backups sichern Konfigurationen.\n",
            encoding="utf-8",
        )
        runner = ToolRunner(vault, allow_edit=True, allow_full_rewrite=True)
        runner._notiz_lesen("Server.md")
        result = runner._notiz_bearbeiten(
            "Server.md", "vollstaendig_neustrukturieren",
            "# Serverbetrieb\n\n## Backups\n\nBackups sichern Konfigurationen.\n\n"
            "## Firewall\n\nDie Firewall schützt Netzwerkdienste.\n",
            grund="Neue Struktur ausdrücklich verlangt",
        )
        content = note.read_text(encoding="utf-8")
        self.assertEqual(result["bearbeitet"], "Server.md")
        self.assertTrue(content.startswith("---\ntags: [it]\nstatus: geprüft\n---"))
        self.assertIn("Firewall schützt Netzwerkdienste", content)
        self.assertIn("Backups sichern Konfigurationen", content)

    def test_full_restructure_rejects_large_content_loss(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        note = vault / "Server.md"
        original = (
            "# Server\n\nFirewall schützt Netzwerkdienste. Backups sichern Konfigurationen. "
            "Monitoring erkennt Ausfälle. Zertifikate verschlüsseln Verbindungen.\n"
        )
        note.write_text(original, encoding="utf-8")
        runner = ToolRunner(vault, allow_edit=True, allow_full_rewrite=True)
        runner._notiz_lesen("Server.md")
        result = runner._notiz_bearbeiten(
            "Server.md", "vollstaendig_neustrukturieren", "# Schönes Design\n\nAlles neu."
        )
        self.assertIn("fehler", result)
        self.assertEqual(note.read_text(encoding="utf-8"), original)

    def test_edit_fallback_never_creates_replacement_note(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        runner = ToolRunner(vault, allow_edit=True)
        requirements = analyse_request("Ändere den Abschnitt Sicherheit in der Notiz.")
        steps = runner.finish_required_actions(requirements, "Ändere die Notiz", "Neuer Text")
        self.assertIn("fehler", steps[0]["result"])
        self.assertEqual(list(vault.rglob("*.md")), [])

    def test_fallback_writes_note_copies_original_and_adds_real_link(self) -> None:
        vault = self.temp / "vault"
        uploads = self.temp / "uploads"
        vault.mkdir()
        with patch.object(attachments, "UPLOAD_DIR", uploads):
            chat_id = "abc12345"
            attachments.store(chat_id, "Quelle.pdf", b"original-pdf")
            requirements = analyse_request(
                "Erstelle eine Notiz zu den Informationen.", ["Quelle.pdf"]
            )
            runner = ToolRunner(vault, chat_id=chat_id, attachment_dir="90 Anhänge")
            steps = runner.finish_required_actions(
                requirements,
                "Erstelle eine Notiz zu den Informationen.",
                "# Informationen\n\nEine fachlich strukturierte Erklärung.",
            )

        self.assertTrue(steps)
        self.assertFalse(runner.missing_actions(requirements))
        note = vault / Path(runner.note_files[-1])
        content = note.read_text(encoding="utf-8")
        stored = runner.stored_attachments["Quelle.pdf"]["abgelegt"]
        self.assertIn(stored, content)
        self.assertEqual((vault / Path(stored)).read_bytes(), b"original-pdf")

    def test_attachment_link_is_replaced_by_exact_stored_path(self) -> None:
        vault = self.temp / "vault"
        uploads = self.temp / "uploads"
        vault.mkdir()
        with patch.object(attachments, "UPLOAD_DIR", uploads):
            chat_id = "deadbeef"
            attachments.store(chat_id, "Quelle.pdf", b"pdf")
            runner = ToolRunner(vault, chat_id=chat_id, attachment_dir="90 Anhänge")
            stored = runner._anhang_in_vault_ablegen("Quelle.pdf")
            runner._notiz_erstellen(
                "Wissen.md",
                "# Wissen\n\n*Diese Notiz basiert ausschließlich auf den angehängten PDFs und Bildern.*\n\n"
                "## Quellen\n\n- [[Quelle.pdf]]\n",
            )
            result = runner.ensure_attachment_links()

        content = (vault / "Wissen.md").read_text(encoding="utf-8")
        self.assertIsNotNone(result)
        self.assertNotIn("basiert ausschließlich", content)
        self.assertNotIn("[[Quelle.pdf]]", content)
        self.assertIn(stored["einbetten_als"], content)
        self.assertEqual(stored["abgelegt"], "90 Anhänge/Quelle.pdf")

    def test_nonexistent_pdf_source_link_is_not_written(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        runner = ToolRunner(vault)

        result = runner._notiz_erstellen(
            "Wissen.md", "# Wissen\n\n## Quellen\n\n- [[Erfundene Quelle.pdf]]\n"
        )

        self.assertIn("fehler", result)
        self.assertIn("nicht vorhanden", result["fehler"])
        self.assertFalse((vault / "Wissen.md").exists())

    def test_batch_edit_scans_every_markdown_file_and_fixes_real_links(self) -> None:
        vault = self.temp / "vault"
        module = vault / "Spanisch" / "01_Vokabeln"
        module.mkdir(parents=True)
        (vault / "Start.md").write_text(
            "# Start\n\n- [[Spanisch/01_Vokabeln]]\n", encoding="utf-8"
        )
        (vault / "Unveraendert.md").write_text("# Ohne Symbole\n", encoding="utf-8")
        (vault / "Spanisch" / "00_Inhalt.md").write_text(
            "# 🇪🇸 Inhalt\n\n- [📖 Vokabeln](./01_Vokabeln/README.md)\n",
            encoding="utf-8",
        )
        (module / "README.md").write_text(
            "# 📖 Vokabeln\n\n- [[../../Start]]\n\n```markdown\n# 😀 Beispiel\n```\n",
            encoding="utf-8",
        )
        requirements = analyse_request(
            "Entferne alle Emojis und ersetze alle relativen Links durch korrekte WikiLinks.",
            context_messages=["Von allen Dateien"],
        )
        runner = ToolRunner(
            vault,
            allow_edit=requirements.requires_edit,
            batch_edit_operations=requirements.batch_edit_operations,
        )

        steps = runner.finish_required_actions(requirements, "Auftrag", "")

        self.assertFalse(runner.missing_actions(requirements))
        result = steps[0]["result"]
        self.assertEqual(result["geprueft"], 4)
        self.assertEqual(result["geaendert"], 3)
        index = (vault / "Spanisch" / "00_Inhalt.md").read_text(encoding="utf-8")
        readme = (module / "README.md").read_text(encoding="utf-8")
        self.assertIn("[[Spanisch/01_Vokabeln/README|Vokabeln]]", index)
        self.assertIn("[[Start]]", readme)
        self.assertIn(
            "[[Spanisch/01_Vokabeln/README]]",
            (vault / "Start.md").read_text(encoding="utf-8"),
        )
        self.assertNotIn("🇪🇸", index)
        self.assertNotIn("📖 Vokabeln", readme.split("```markdown", 1)[0])
        self.assertIn("😀 Beispiel", readme)  # Codebeispiele bleiben unverändert.

        # Auch ohne weiteren Änderungsbedarf ist der vollständige zweite Lauf
        # abgeschlossen und darf keine Einzeldatei-Bearbeitung verlangen.
        second_runner = ToolRunner(
            vault,
            allow_edit=requirements.requires_edit,
            batch_edit_operations=requirements.batch_edit_operations,
        )
        second_result = second_runner._markdown_dateien_bereinigen(
            operationen=list(requirements.batch_edit_operations)
        )
        self.assertEqual(second_result["geaendert"], 0)
        self.assertEqual(second_runner.missing_actions(requirements), [])

    def test_file_organization_moves_sources_and_updates_every_link(self) -> None:
        vault = self.temp / "vault"
        topic = vault / "Thema"
        unrelated = vault / "Nur-Dateien"
        topic.mkdir(parents=True)
        unrelated.mkdir()
        ensure_vault_guide(vault)
        (topic / "README.md").write_text(
            "# Thema\n\n- [[Thema/Quelle.pdf|Quelle]]\n"
            "- [Bild](./Bild.png)\n",
            encoding="utf-8",
        )
        (topic / "Quelle.pdf").write_bytes(b"pdf")
        (topic / "Bild.png").write_bytes(b"png")
        (unrelated / "Archiv.pdf").write_bytes(b"archiv")
        requirements = analyse_request(
            "Lege PDFs und Bilder immer in einen Unterordner mit Dateien."
        )
        runner = ToolRunner(
            vault,
            allow_file_organization=requirements.organize_vault_files,
        )

        steps = runner.finish_required_actions(requirements, "Auftrag", "")

        self.assertEqual(runner.missing_actions(requirements), [])
        result = steps[0]["result"]
        self.assertEqual(result["verschoben_anzahl"], 2)
        self.assertTrue((topic / "Dateien" / "Quelle.pdf").is_file())
        self.assertTrue((topic / "Dateien" / "Bild.png").is_file())
        self.assertFalse((topic / "Quelle.pdf").exists())
        self.assertTrue((unrelated / "Archiv.pdf").is_file())
        content = (topic / "README.md").read_text(encoding="utf-8")
        self.assertIn("[[Thema/Dateien/Quelle.pdf|Quelle]]", content)
        self.assertIn("[[Thema/Dateien/Bild.png|Bild]]", content)
        guide = (vault / "00 Inhalt.md").read_text(encoding="utf-8")
        self.assertIn("Unterordner `Dateien`", guide)
        self.assertIn("[[Thema/Dateien/Quelle.pdf|Quelle.pdf]]", guide)

        second = ToolRunner(vault, allow_file_organization=True)
        second_result = second._dateien_in_unterordner_verschieben()
        self.assertEqual(second_result["verschoben_anzahl"], 0)
        self.assertTrue(second.file_organization_done)

    def test_common_tool_name_typo_is_accepted(self) -> None:
        vault = self.temp / "vault"
        vault.mkdir()
        note = vault / "Notiz.md"
        note.write_text("# Notiz\n", encoding="utf-8")
        runner = ToolRunner(vault)

        result = asyncio.run(runner.run(
            "notiz_ergaetzen",
            {"pfad": "Notiz.md", "inhalt": "Ergänzung."},
        ))

        self.assertEqual(result["ergaenzt"], "Notiz.md")
        self.assertIn("Ergänzung.", note.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
