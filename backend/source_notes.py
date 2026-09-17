"""Bild-/Scan-Arbeitsnotizen ohne weitere Modellrunde suchbar machen."""
import hashlib
import json
from pathlib import Path

from . import attachments
from .vault import read_text_file, safe_join


def has_visual_content(record):
    return any(key == 'image' or key.startswith('image:') or ':vision' in key or key.startswith('word/media/')
               for key in record.get('parts', {}))


def save_source_note(runner, name, text, record, data_dir):
    """Bewahrt OCR vollständig; nur der Quellenkopf ist kurz."""
    if not text.strip() or not has_visual_content(record):
        return None
    source = runner._anhang_in_vault_ablegen(name)
    if 'fehler' in source:
        return source
    vault_key = hashlib.sha256(str(runner.root.resolve()).encode()).hexdigest()[:16]
    ledger = Path(data_dir) / 'source-notes' / vault_key / (runner.chat_id + '.json')
    saved = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
    digest = hashlib.sha256((source['abgelegt'] + '\0' + text).encode()).hexdigest()
    previous = saved.get(digest)
    if previous and safe_join(runner.root, previous['path']).is_file():
        content = read_text_file(runner.root, previous['path'])['content']
        if hashlib.sha256(content.encode()).hexdigest() == previous['hash']:
            return {'quellennotiz': previous['path'], 'wiederverwendet': True}
    title = attachments.safe_filename(Path(name).stem)
    status = 'vollständig ausgewertet' if record.get('complete') else 'unvollständig; Leselücken prüfen'
    # OCR ist Quelldatenmaterial: erkannte Wiki-Syntax nicht als erfundene Datei verlinken.
    literal_text = text.replace('[[', r'\[\[')
    content = (f'---\ntyp: bild-scan-quelle\n---\n\n# Quelle: {title}\n\n'
               f"Original: [[{source['abgelegt']}]]\n\n"
               f'Auswertung: {status}. Automatisch erkannter Text; Unsicherheiten aus der Auswertung beachten.\n\n'
               f'## Erkannter Text und Bildwissen\n\n{literal_text}\n')
    result = runner._notiz_erstellen(f'91 Quellenwissen/{title}.md', content)
    if 'erstellt' not in result:
        return result
    path = result['erstellt']
    # Quellennotizen ersetzen nicht die ausdrücklich beauftragte Wissensnotiz.
    runner.note_files.remove(path)
    actual = read_text_file(runner.root, path)['content']
    saved[digest] = {'path': path, 'hash': hashlib.sha256(actual.encode()).hexdigest()}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    temp = ledger.with_suffix('.tmp')
    temp.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
    temp.replace(ledger)
    return {'quellennotiz': path, 'original': source['abgelegt']}
