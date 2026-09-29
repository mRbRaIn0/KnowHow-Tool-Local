"""V1.5: Sprache (Deutsch/Englisch) im Backend, Suchbereich und vom Server erzeugte Texte."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend import i18n
from backend.config import ConfigStore, Profile
from backend.database import Database
from backend.routers import chat, settings


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setattr(i18n, 'language', lambda: 'en')


def test_every_backend_message_exists_in_both_languages():
    for key, (german, english_text) in i18n.MESSAGES.items():
        assert german.strip() and english_text.strip(), key
        assert german != english_text or key in {'work.stored'}, key
    assert i18n.bt('sources') == 'Quellen'


def test_bt_and_localize_follow_the_selected_language(english):
    assert i18n.bt('sources') == 'Sources'
    assert i18n.bt('batch.done', n=3).startswith('Done. All 3 Markdown files')
    assert i18n.localize('Chat nicht gefunden.') == 'Chat not found.'
    assert i18n.localize('Pfad liegt außerhalb des Vaults: ../x') == 'Path is outside the vault: ../x'
    assert i18n.localize('[[A/B.md]] ergänzt.') == '[[A/B.md]] extended.'
    assert i18n.localize('Das Modell \'x\' ist in Ollama nicht installiert.') == "The model 'x' is not installed in Ollama."
    assert i18n.localize('Unerwarteter Fehler: kaputt') == 'Unexpected error: kaputt'
    assert i18n.localize('völlig unbekannter Text') == 'völlig unbekannter Text'
    assert i18n.localize_detail({'message': 'Die Nachricht ist leer.', 'kind': 'empty'}) == {
        'message': 'The message is empty.', 'kind': 'empty'}
    assert i18n.localize_detail('Ordner nicht gefunden.') == 'Folder not found.'
    assert 'Englisch' in i18n.language_rule()


def test_german_stays_untouched():
    assert i18n.localize('Chat nicht gefunden.') == 'Chat nicht gefunden.'
    assert i18n.language_rule() == ''
    assert i18n.bt('work.savedOne', path='A.md') == 'Im Vault gespeichert: `A.md`'


def test_confirmations_and_titles_speak_english(english):
    assert chat._change_confirmation(['A.md']) == 'Saved in the vault: `A.md`'
    assert chat._change_confirmation([]).startswith('The requested vault task')
    assert 'Erstellt' not in chat._batch_confirmation([])
    assert chat._title_from('') == 'New chat'
    assert chat._incomplete_confirmation(['edit']).startswith('The existing note was not overwritten')
    steps = [{'tool': 'dateien_in_unterordner_verschieben', 'ok': True, 'result': {
        'geprueft': 4, 'verschoben_anzahl': 3, 'bereits_eingeordnet': 1, 'unterordner': 'Dateien',
        'geaenderte_notizen': ['A.md']}}]
    text = chat._organization_confirmation(steps)
    assert 'Moved to the subfolder `Dateien`: 3' in text and 'Verschoben' not in text


def test_english_placeholder_titles_are_replaced_by_the_first_question():
    assert 'New question' in chat._PLACEHOLDER_TITLES and 'Neue Frage' in chat._PLACEHOLDER_TITLES
    assert 'New knowledge chat' in chat._PLACEHOLDER_TITLES


def test_undone_markers_recognise_both_languages():
    german, english_text = i18n.MESSAGES['undo.history']
    assert any(mark in german for mark in chat._UNDONE_MARKS)
    assert any(mark in english_text for mark in chat._UNDONE_MARKS)
    assert any(mark in i18n.MESSAGES['work.answerInterrupted'][1] for mark in chat._INTERRUPTED_MARKS)
    assert any(mark in i18n.MESSAGES['work.answerInterrupted'][0] for mark in chat._INTERRUPTED_MARKS)


def _ask_english(tmp_path, monkeypatch, search_result, answer):
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path)})
    db = Database(tmp_path / 'ask.db')
    captured = []

    class Model:
        async def capabilities(self, model):
            return []

        async def chat_stream(self, model, messages, **kwargs):
            captured.append(messages)
            yield {'message': {'content': answer}, 'done': True}

    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: Model())
    monkeypatch.setattr(chat, 'hybrid_search', AsyncMock(return_value=search_result))
    monkeypatch.setattr(chat.knowledge_worker, 'active', lambda: True)

    async def run():
        question = db.create_chat('Question', 'm', 'ask')
        response = await chat.send_message(question['id'], chat.MessageRequest(content='What is 1 + 2?'))
        events = [json.loads(item[6:]) async for item in response.body_iterator]
        return events, db.list_messages(question['id'])[-1]['content']
    try:
        events, stored = asyncio.run(run())
    finally:
        db.close()
    return events, stored, captured


def test_english_answer_gets_language_rule_and_english_sources(tmp_path, monkeypatch, english):
    hits = {'results': [{'path': 'Wissen/Mathe.md', 'page': 0, 'content': '1 + 2 = 3'}]}
    events, stored, captured = _ask_english(tmp_path, monkeypatch, hits, '1 + 2 = 3.')
    assert stored == '1 + 2 = 3.\n\nSources: [[Wissen/Mathe]]'
    assert 'ausschließlich auf Englisch' in captured[0][0]['content']


def test_english_no_hit_marks_step_and_strips_english_hint(tmp_path, monkeypatch, english):
    events, stored, _ = _ask_english(tmp_path, monkeypatch, {'results': []}, 'No entry found – AI knowledge: 3')
    assert stored == '3'
    step = next(e for e in events if e.get('tool') == 'wissenssuche')
    assert step['result']['kein_treffer'] is True


def test_ui_language_is_saved_validated_and_defaults_to_german(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path / 'config.json')
    monkeypatch.setattr(settings, 'store', store)
    assert store.load().ui.language == 'de'
    result = asyncio.run(settings.update_ui(settings.UIPatch(language='en')))
    assert result['language'] == 'en' and result['theme'] == 'system'
    assert json.loads((tmp_path / 'config.json').read_text(encoding='utf-8'))['ui']['language'] == 'en'
    asyncio.run(settings.update_ui(settings.UIPatch(theme='dark')))
    assert store.config.ui.language == 'en' and store.config.ui.theme == 'dark'
    with pytest.raises(HTTPException) as unknown:
        asyncio.run(settings.update_ui(settings.UIPatch(language='fr')))
    assert unknown.value.status_code == 400
    with pytest.raises(HTTPException):
        asyncio.run(settings.update_ui(settings.UIPatch(theme='neon')))


def test_undo_message_is_written_in_the_ui_language(english):
    text = i18n.bt('undo.message', paths='A.md, B.md')
    assert text == 'The last vault task was undone. Restored files: A.md, B.md'
    assert any(mark in text for mark in chat._UNDONE_MARKS)


@pytest.mark.parametrize('text,names,edit,rewrite,mode', [
    ('Completely restructure this note, keeping all information: [[Projekt/Notiz]]', (), True, True, 'edit'),
    ('Analyse the attached image and create a structured note from it with the image embedded.', ('a.png',), False, False, 'create'),
    ('Store the attached files in the vault and document their content.', ('a.png',), False, False, 'organise'),
    ('Store the attached file in the vault and summarise it.', ('a.pdf',), False, False, 'organise'),
    ('Extend an existing note with this information.', (), False, False, 'update'),
    ('Create a structured note from my details.', (), False, False, 'create'),
    ('What is the capital of France?', (), False, False, ''),
])
def test_english_ui_prompts_trigger_the_same_vault_tasks(text, names, edit, rewrite, mode):
    from backend.workflow import analyse_request
    requirements = analyse_request(text, names)
    assert (requirements.requires_edit, requirements.allow_full_rewrite, requirements.mode) == (edit, rewrite, mode)


def test_vault_index_and_syntax_reference_are_never_answer_sources():
    from backend.knowledge import relevant_results
    hits = [{'path': '00 Inhalt.md', 'content': '[[IT/Azure/Arc|Arc]] Azure Arc'},
            {'path': 'Obsidian_Syntax.md', 'content': 'Azure Arc Beispiel'},
            {'path': 'IT/Azure/Arc.md', 'content': 'Azure Arc verwaltet Server.'}]
    assert [item['path'] for item in relevant_results('Was ist Azure Arc?', hits)] == ['IT/Azure/Arc.md']
