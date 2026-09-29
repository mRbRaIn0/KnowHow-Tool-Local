"""V1.4 Funktion A: schnelle, ehrliche Antworten im Fragen-Chat."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend.config import Profile
from backend.database import Database
from backend.knowledge import hybrid_search, query_terms, relevant_results, sync_index
from backend.routers import chat


@pytest.mark.parametrize('question,terms', [
    ('Was ist 1 + 2?', []),
    ('Erkläre mir bitte kurz, was KI ist.', ['ki']),
    ('Welche Wartungsschritte gelten für ZX-731?', ['wartungsschritte', 'zx', '731']),
    ('Wie funktioniert Docker in 3 Sätzen?', ['docker']),
    ('Was ist S7?', ['s7']),
])
def test_query_terms_drop_filler_words(question, terms):
    assert query_terms(question) == terms


def test_relevance_needs_real_coverage():
    results = [
        {'path': 'Docker.md', 'content': 'Docker Volumes speichern Daten.'},
        {'path': 'Kochen.md', 'content': 'Was ist das beste Rezept? Die Soße.'},
        {'path': 'Skizze.md', 'content': 'Eine Skizze.'},
        {'path': 'Ähnlich.md', 'content': 'nichts Wörtliches', 'distance': 0.7},
    ]
    assert [r['path'] for r in relevant_results('Was ist Docker?', results)] == ['Docker.md', 'Ähnlich.md']
    # Kurze Kennungen nur am Wortanfang.
    assert [r['path'] for r in relevant_results('Was ist KI?', results)] == ['Ähnlich.md']
    assert relevant_results('Was ist 1 + 2?', results) == []


def test_search_without_terms_touches_neither_index_nor_model(tmp_path):
    class Untouchable:
        def __getattr__(self, name):
            raise AssertionError('no index or model access for ' + name)
    result = asyncio.run(hybrid_search(tmp_path, Untouchable(), '1 + 2', Untouchable(), 'embed'))
    assert result['results'] == [] and result['skipped']


def test_irrelevant_filler_matches_are_filtered(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / 'Docker.md').write_text('# Docker\n\nDocker Volumes speichern Containerdaten.', encoding='utf-8')
    (vault / 'Kochen.md').write_text('# Kochen\n\nWas ist wichtig? Die Soße ist das Wichtigste.', encoding='utf-8')
    db = Database(tmp_path / 'app.db')
    try:
        asyncio.run(sync_index(vault, db, None, ''))
        docker = asyncio.run(hybrid_search(vault, db, 'Was ist Docker?', None, '', refresh=False, relevant_only=True))
        missing = asyncio.run(hybrid_search(vault, db, 'Was ist Kubernetes?', None, '', refresh=False, relevant_only=True))
    finally:
        db.close()
    assert [item['path'] for item in docker['results']] == ['Docker.md']
    assert missing['results'] == []


def _ask(tmp_path, monkeypatch, search_result, answer, scope=None):
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path)})
    db = Database(tmp_path / 'ask.db')
    captured = []

    class Model:
        async def capabilities(self, model):
            return []

        async def chat_stream(self, model, messages, **kwargs):
            captured.append(messages)
            yield {'message': {'content': answer}, 'done': True}

    search = AsyncMock(return_value=search_result)
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: Model())
    monkeypatch.setattr(chat, 'hybrid_search', search)
    monkeypatch.setattr(chat.knowledge_worker, 'active', lambda: True)

    async def run():
        question = db.create_chat('Frage', 'm', 'ask')
        response = await chat.send_message(question['id'], chat.MessageRequest(content='Was ist 1 + 2?', scope=scope))
        events = [json.loads(item[6:]) async for item in response.body_iterator]
        return events, db.list_messages(question['id'])[-1]['content']
    try:
        events, stored = asyncio.run(run())
    finally:
        db.close()
    return events, stored, captured, search


def test_no_vault_hit_is_marked_for_the_ui_and_never_in_the_answer(tmp_path, monkeypatch):
    events, stored, captured, search = _ask(
        tmp_path, monkeypatch, {'results': []}, 'Kein Eintrag gefunden – KI-Wissen: 1 + 2 = 3')
    assert stored == '1 + 2 = 3'
    assert events[-1]['content'] == stored
    assert not any('Kein Eintrag' in e.get('delta', '') for e in events if e['type'] == 'content')
    assert search.await_args.kwargs['refresh'] is False
    assert search.await_args.kwargs['relevant_only'] is True
    prompt = captured[0][-1]['content']
    assert 'keinen passenden Eintrag' in prompt and 'Kein Eintrag gefunden' not in prompt
    step = next(e for e in events if e.get('tool') == 'wissenssuche')
    assert step['result'] == {'anzahl': 0, 'kein_treffer': True}


@pytest.mark.parametrize('pieces,expected', [
    (['**Kein Eintrag gefunden', ' – KI-Wissen:**', '\n\n1 + 2 = 3.'], '1 + 2 = 3.'),
    (['Kein Eintrag gefunden – KI-Wissen:\nKein Eintrag gefunden – KI-Wissen:\n1 + 2 = 3.'], '1 + 2 = 3.'),
    (['No entry found', ' – AI knowledge: 3'], '3'),
    (['Kein Eintrag im Vault.\n\nDie Summe ist 3.'], 'Die Summe ist 3.'),
    (['1 + 2 = 3'], '1 + 2 = 3'),
    (['Note the knowledge base: nothing.'], 'Note the knowledge base: nothing.'),
    (['Keine Sorge, das ist einfach.\n\nEs ist 3.'], 'Keine Sorge, das ist einfach.\n\nEs ist 3.'),
])
def test_leading_hint_filter_removes_only_a_repeated_hint(pieces, expected):
    hint = chat.LeadingHintFilter(True)
    shown = ''.join(hint.feed(piece) for piece in pieces) + hint.flush()
    assert shown == expected
    plain = chat.LeadingHintFilter(False)
    assert ''.join(plain.feed(piece) for piece in pieces) == ''.join(pieces)


def test_vault_answer_gets_source_links_when_missing(tmp_path, monkeypatch):
    hits = {'results': [{'path': 'Wissen/Mathe.md', 'page': 0, 'content': '1 + 2 = 3'},
                        {'path': 'Wissen/Mathe.md', 'page': 0, 'content': 'Addition'}]}
    _, stored, captured, _ = _ask(tmp_path, monkeypatch, hits, '1 + 2 = 3.')
    assert stored == '1 + 2 = 3.\n\nQuellen: [[Wissen/Mathe]]'
    assert 'Kein Eintrag' not in stored
    assert 'Wissen/Mathe.md' in captured[0][-1]['content']


def test_cited_answer_keeps_its_own_links(tmp_path, monkeypatch):
    hits = {'results': [{'path': 'Wissen/Mathe.md', 'page': 0, 'content': '1 + 2 = 3'}]}
    _, stored, _, _ = _ask(tmp_path, monkeypatch, hits, '1 + 2 = 3 laut [[Mathe]].')
    assert stored == '1 + 2 = 3 laut [[Mathe]].'


def test_question_history_is_short_and_without_work_state(tmp_path):
    db = Database(tmp_path / 'history.db')
    try:
        question = db.create_chat('Frage', 'm', 'ask')
        for index in range(12):
            db.add_message(question['id'], 'user', f'Frage {index} ' + 'x' * 900)
            db.add_message(question['id'], 'assistant', f'Antwort {index}',
                           sources=[{'tool': 'wissenssuche', 'result': {'anzahl': 1}, 'ok': True}])
        history = chat._build_history(db, question['id'], 'System', max_chars=4000,
                                      include_work_state=False)
    finally:
        db.close()
    text = json.dumps(history, ensure_ascii=False)
    assert 'Gespeicherter Arbeitsstand' not in text
    assert 'Frage 11' in text and 'Frage 0 ' not in text


def test_repeated_reads_and_searches_are_not_executed_again():
    seen = {}
    assert chat._repeated_call('vault_suchen', {'suchbegriff': 'Docker'}, seen) is None
    chat._remember_call('vault_suchen', {'suchbegriff': 'Docker'}, {'treffer': []}, seen)
    assert 'Bereits' in chat._repeated_call('vault_suchen', {'suchbegriff': 'Docker'}, seen)['hinweis']
    chat._remember_call('vault_suchen', {'suchbegriff': 'Volumes'}, {'treffer': []}, seen)
    assert 'Suchlimit' in chat._repeated_call('vault_suchen', {'suchbegriff': 'Neu'}, seen)['hinweis']

    read = {'pfad': 'A.md'}
    chat._remember_call('notiz_lesen', read, {'inhalt': 'alt'}, seen)
    assert chat._repeated_call('notiz_lesen', read, seen)
    assert chat._repeated_call('notiz_lesen', {'pfad': 'A.md', 'offset': 6000}, seen) is None
    chat._remember_call('notiz_ergaenzen', {'pfad': 'A.md'}, {'ergaenzt': 'A.md'}, seen)
    assert chat._repeated_call('notiz_lesen', read, seen) is None
    # Fehlgeschlagene Aufrufe dürfen wiederholt werden; Schreibwerkzeuge nie blockieren.
    chat._remember_call('ordner_auflisten', {'pfad': 'X'}, {'fehler': 'weg'}, seen)
    assert chat._repeated_call('ordner_auflisten', {'pfad': 'X'}, seen) is None
    assert chat._repeated_call('notiz_erstellen', {'pfad': 'B.md'}, seen) is None


def test_scope_path_normalizes_and_rejects_everything_outside(tmp_path):
    (tmp_path / 'IT' / 'Azure').mkdir(parents=True)
    assert chat._scope_path(tmp_path, r'IT\Azure') == 'IT/Azure/'
    assert chat._scope_path(tmp_path, '/IT/') == 'IT/'
    for invalid in ('', None, '../draussen', 'Fehlt', '.'):
        assert chat._scope_path(tmp_path, invalid) == ''


def test_selected_folder_limits_the_search_to_that_folder(tmp_path, monkeypatch):
    (tmp_path / 'IT' / 'Azure').mkdir(parents=True)
    events, _, _, search = _ask(tmp_path, monkeypatch, {'results': []}, '3', scope='IT/Azure')
    assert search.await_args.kwargs['focus'].paths == ('IT/Azure/',)
    step = next(e for e in events if e.get('tool') == 'wissenssuche')
    assert step['arguments']['bereich'] == 'IT/Azure'
    events, _, _, search = _ask(tmp_path, monkeypatch, {'results': []}, '3')
    assert search.await_args.kwargs['focus'].paths is None  # Standard: alle Ordner


def test_folder_scope_still_filters_irrelevant_hits(tmp_path):
    from backend.context_focus import VaultFocus
    from backend.database import Database
    vault = tmp_path / 'vault'
    (vault / 'IT').mkdir(parents=True)
    (vault / 'IT' / 'Kochen.md').write_text('# Kochen\n\nWas ist wichtig? Die Soße.', encoding='utf-8')
    (vault / 'IT' / 'Docker.md').write_text('# Docker\n\nDocker Volumes speichern Daten.', encoding='utf-8')
    db = Database(tmp_path / 'scope.db')
    try:
        asyncio.run(sync_index(vault, db, None, ''))
        result = asyncio.run(hybrid_search(vault, db, 'Was ist Docker?', None, '', refresh=False,
                                           relevant_only=True, focus=VaultFocus(('IT/',))))
    finally:
        db.close()
    assert [item['path'] for item in result['results']] == ['IT/Docker.md']
