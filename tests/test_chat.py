from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database import Database
from backend.routers.chat import (
    _batch_confirmation,
    _question_system_prompt,
    _response_needs_continuation,
    _system_prompt,
    _tool_rounds,
)


class ChatSummaryTests(unittest.TestCase):
    def test_batch_confirmation_uses_verified_tool_counts(self) -> None:
        summary = _batch_confirmation([
            {
                "tool": "markdown_dateien_bereinigen",
                "ok": True,
                "result": {
                    "operationen": ["fix_relative_links"],
                    "geprueft": 8,
                    "geaendert": 1,
                    "unveraendert": 7,
                    "geaenderte_dateien": ["Spanisch/README.md"],
                    "nicht_aufloesbare_links": [],
                },
            }
        ])

        self.assertIn("Alle 8 Markdown-Dateien", summary)
        self.assertIn("Geändert: 1", summary)
        self.assertIn("Ordner-WikiLinks", summary)
        self.assertIn("`Spanisch/README.md`", summary)
        self.assertIn("Nicht auflösbare Links: 0", summary)

    def test_announced_but_unfinished_work_is_continued(self) -> None:
        self.assertTrue(_response_needs_continuation(
            "Ich lese zuerst diese Notiz, um den genauen Inhalt zu sehen."
        ))
        self.assertTrue(_response_needs_continuation(
            "Der Vault enthält nun ausschließlich"
        ))
        self.assertTrue(_response_needs_continuation("Vollständig.", "length"))
        self.assertFalse(_response_needs_continuation(
            "Fertig. Alle acht Dateien wurden geprüft und die Links aktualisiert."
        ))

    def test_tool_budget_allows_longer_workflows(self) -> None:
        self.assertEqual(_tool_rounds(0), 18)
        self.assertEqual(_tool_rounds(60), 120)

    def test_chat_modes_have_separate_instructions(self) -> None:
        vault_prompt = _system_prompt("", None)
        question_prompt = _question_system_prompt("")

        self.assertIn("WISSEN ERWEITERN", vault_prompt)
        self.assertIn("keine reinen Wissensfragen", vault_prompt)
        self.assertIn("WISSEN FRAGEN", question_prompt)
        self.assertIn("keinen Schreibzugriff", question_prompt)
        self.assertIn("allgemeinen Modellwissen ergänzen", question_prompt)


class ChatPurposeMigrationTests(unittest.TestCase):
    def test_existing_chats_become_vault_chats_and_lists_are_filtered(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "app.db"
            connection = sqlite3.connect(path)
            connection.execute(
                """CREATE TABLE chats (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                "INSERT INTO chats VALUES (?,?,?,?,?)",
                ("alt", "Bestehender Chat", "modell", "2026-01-01", "2026-01-01"),
            )
            connection.commit()
            connection.close()

            database = Database(path)
            try:
                self.assertEqual(database.get_chat("alt")["purpose"], "vault")
                question = database.create_chat("Neue Frage", "modell", "ask")

                self.assertEqual([c["id"] for c in database.list_chats(purpose="vault")], ["alt"])
                self.assertEqual(
                    [c["id"] for c in database.list_chats(purpose="ask")],
                    [question["id"]],
                )
            finally:
                database.close()


class ChatMessageSchemaUpgradeTests(unittest.TestCase):
    def test_old_messages_keep_text_after_column_migration(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "app.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE chats (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                INSERT INTO chats VALUES ('alt', 'Bestehender Chat', 'modell',
                                          '2026-01-01', '2026-01-01');
                INSERT INTO messages (chat_id, role, content, created_at)
                VALUES ('alt', 'user', 'Bitte behalten', '2026-01-01'),
                       ('alt', 'assistant', 'Antwort bleibt', '2026-01-01');
                """
            )
            connection.commit()
            connection.close()

            database = Database(path)
            try:
                chat = database.get_chat("alt")
                messages = database.list_messages("alt")
                self.assertEqual(chat["title"], "Bestehender Chat")
                self.assertEqual(chat["purpose"], "vault")
                self.assertEqual([item["content"] for item in messages],
                                 ["Bitte behalten", "Antwort bleibt"])
                self.assertEqual(messages[1]["thinking"], "")
                self.assertEqual(messages[1]["attachments"], [])
            finally:
                database.close()


class ChatFolderTests(unittest.TestCase):
    def _database(self, folder: str) -> Database:
        return Database(Path(folder) / "app.db")

    def test_chats_can_be_filed_archived_and_survive_folder_deletion(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            database = self._database(folder)
            try:
                projekt = database.create_folder("Projekt", "vault")
                chat = database.create_chat("Notizen", "modell", "vault")
                self.assertIsNone(chat["folder_id"])
                self.assertFalse(chat["archived"])

                database.move_chat(chat["id"], projekt["id"])
                self.assertEqual(database.get_chat(chat["id"])["folder_id"], projekt["id"])
                self.assertEqual(database.list_folders("vault")[0]["chat_count"], 1)

                database.set_chat_archived(chat["id"], True)
                self.assertTrue(database.get_chat(chat["id"])["archived"])

                database.delete_folder(projekt["id"])
                self.assertEqual(database.list_folders("vault"), [])
                blieb = database.get_chat(chat["id"])
                self.assertIsNotNone(blieb)
                self.assertIsNone(blieb["folder_id"])
            finally:
                database.close()

    def test_folders_are_separate_per_purpose_and_unknown_targets_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            database = self._database(folder)
            try:
                database.create_folder("Arbeit", "vault")
                fragen = database.create_folder("Fragen", "ask")

                self.assertEqual([f["name"] for f in database.list_folders("vault")], ["Arbeit"])
                self.assertEqual([f["name"] for f in database.list_folders("ask")], ["Fragen"])

                chat = database.create_chat("Frage", "modell", "ask", "gibt-es-nicht")
                self.assertIsNone(chat["folder_id"])

                database.move_chat(chat["id"], fragen["id"])
                database.move_chat(chat["id"], "")
                self.assertIsNone(database.get_chat(chat["id"])["folder_id"])
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
