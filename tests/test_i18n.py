"""V1.5: zentrale Übersetzungen (Deutsch/Englisch) sind vollständig und werden korrekt verwendet."""
import json
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'
PLACEHOLDER = re.compile(r'\{(\w+)\}')


def load(code):
    return json.loads((FRONTEND / 'i18n' / f'{code}.json').read_text(encoding='utf-8'))


def test_both_languages_have_identical_keys_and_placeholders():
    german, english = load('de'), load('en')
    assert set(german) == set(english), sorted(set(german) ^ set(english))
    for key in german:
        assert german[key].strip() and english[key].strip(), key
        assert set(PLACEHOLDER.findall(german[key])) == set(PLACEHOLDER.findall(english[key])), key
        assert 'null' not in (german[key].lower().split()) and 'undefined' not in english[key].lower().split()


def test_english_is_really_english():
    german, english = load('de'), load('en')
    same = [key for key in german if german[key] == english[key]]
    # Erlaubt: Eigennamen, Produktbegriffe und gleich geschriebene Wörter.
    assert len(same) < len(german) * 0.08, same
    umlauts = [key for key, value in english.items() if re.search('[äöüÄÖÜß]', value)]
    assert not umlauts, umlauts


def used_keys():
    keys = {}
    sources = list((FRONTEND / 'js').rglob('*.js'))
    for path in sources:
        text = path.read_text(encoding='utf-8')
        for match in re.finditer(r"\bt\(\s*'([\w.]+)'", text):
            keys.setdefault(match.group(1), path.name)
    namespaces = {key.split('.')[0] for key in load('de')}
    for path in sources:
        for match in re.finditer(r"'([a-z]+(?:\.[A-Za-z0-9]+)+)'", path.read_text(encoding='utf-8')):
            if match.group(1).split('.')[0] in namespaces:
                keys.setdefault(match.group(1), path.name)
    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    for match in re.finditer(r'data-i18n(?:-\w+)?="([\w.]+)"', html):
        keys.setdefault(match.group(1), 'index.html')
    return keys


def test_every_key_used_in_the_ui_exists_in_both_languages():
    german, english = load('de'), load('en')
    missing = {key: source for key, source in used_keys().items()
               if key not in german or key not in english}
    assert not missing, missing


def test_no_unused_keys_pile_up():
    used = used_keys()
    dynamic = ('mode.', 'step.', 'ctx.', 'variants.', 'attach.', 'cheat.', 'lang.', 'error.', 'status.', 'time.', 'toast.')
    unused = [key for key in load('de') if key not in used and not key.startswith(dynamic)]
    assert len(unused) < 40, unused


def test_static_html_texts_are_translated_at_runtime():
    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    visible = re.findall(r'<span(?![^>]*data-i18n)[^>]*>([A-ZÄÖÜ][^<]{2,})</span>', html)
    assert visible == [] or all(text in ('Ollama', 'Vault', 'KnowHow Tool', 'Privat') or text.startswith('Version')
                                for text in visible), visible
