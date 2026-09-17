"""Literal file commands: deterministic planning, exact resolution, no inference."""
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import re
import time

from .vault import VaultError, iter_files, safe_join, to_relative, write_text_file
from .vault_actions import before_change, after_change


@dataclass
class FileAction:
    action: str
    file: str
    folder: str = ''
    content: str | None = None
    destination: str = ''


# Delimited targets can contain spaces; bare targets deliberately cannot.
REF = r'(?:`[^`\n]+`|"[^"\n]+"|„[^“\n]+“|\[\[[^\]\n]+\]\]|[\w./\\-]*[\w/-])'
FILE = rf'(?:(?:die|der|eine|einer|vorhandenen?|bestehenden?)\s+)*(?:(?:Markdown[- ]?)?(?:Datei|Notiz)\s+)?(?P<file>{REF})'
FOLDER = rf'(?:\s+im\s+Ordner\s+(?P<folder>{REF}))?'


def unquote(value):
    return value.strip().strip('`"„“').removeprefix('[[').removesuffix(']]').replace('\\', '/')


def concrete_reference(raw, command):
    name = unquote(raw).casefold()
    if name in {'datei', 'notiz', 'text', 'zusammenfassung', 'dokumentation', 'alle', 'alles', 'mir'}:
        return False
    return (raw.startswith(('`', '"', '„', '[[')) or '/' in name or '.' in name
            or bool(re.search(r'\d', name))
            or bool(re.search(r'\b(?:Datei|Notiz)\s+' + re.escape(raw) + r'(?:\s|$|:)', command, re.I)))


def parse_file_action(prompt: str) -> FileAction | None:
    # Only literal text after an explicit delimiter is copied. No text generation
    # or multi-action command is ever inferred by this parser.
    text = re.sub(r'^\s*bitte\s+', '', prompt, flags=re.I).lstrip()
    patterns = [
        ('append', rf'(?:Füge|Fuege)\s+(?:diesen|folgenden|den)\s+Text\s+(?:zu|zur|zu der|in)\s+{FILE}{FOLDER}\s+hinzu'),
        ('append', rf'(?:Hänge|Haenge)\s+(?:diesen|folgenden|den)\s+Text\s+an\s+{FILE}{FOLDER}\s+an'),
        ('append', rf'(?:Ergänze|Ergaenze)\s+{FILE}{FOLDER}\s+(?:um|mit)(?:\s+(?:diesen|folgendem|folgenden|dem folgenden)\s+Text)?'),
        ('create', rf'(?:Erstelle|Lege)\s+{FILE}{FOLDER}(?:\s+an)?(?:\s+mit\s+(?:dem\s+)?(?:Inhalt|Text))?'),
    ]
    for action, pattern in patterns:
        match = re.fullmatch(pattern + r'(?:[ \t]*:[ \t]*(?:\r?\n)?(?P<content>[\s\S]*)|[ \t]*\r?\n(?P<lines>[\s\S]*)|[.!]?)', text, re.I)
        if match:
            data = match.groupdict()
            if not concrete_reference(data['file'], text):
                continue
            content = data.get('content') if data.get('content') is not None else data.get('lines')
            return FileAction(action, unquote(data['file']), unquote(data.get('folder') or ''), content)
    for action, pattern in [
        ('delete', rf'(?:Lösche|Loesche|Entferne)\s+{FILE}{FOLDER}'),
        ('find', rf'(?:Suche|Finde|Zeige)\s+{FILE}{FOLDER}'),
        ('rename', rf'(?:Benenne)\s+{FILE}{FOLDER}\s+in\s+(?P<destination>{REF})\s+um'),
        ('move', rf'(?:Verschiebe)\s+{FILE}{FOLDER}\s+(?:nach|in|in den)\s+(?:Ordner\s+)?(?P<destination>{REF})'),
    ]:
        match = re.fullmatch(pattern + r'\s*[.!]?', text, re.I)
        if match:
            data = match.groupdict()
            if not concrete_reference(data['file'], text):
                continue
            return FileAction(action, unquote(data['file']), unquote(data.get('folder') or ''),
                              destination=unquote(data.get('destination') or ''))
    return None


@dataclass
class Resolution:
    path: str
    matches: list[str]


def resolve_file(root: Path, name: str, folder: str = '', markdown=True) -> Resolution:
    """Path > exact filename > exact Markdown stem. Empty files are matches."""
    value = unquote(name)
    if not value or value in {'.', '..'}:
        raise VaultError('Bitte einen konkreten Dateinamen nennen.')
    base = safe_join(root, folder) if folder else root
    requested = safe_join(root, f'{folder}/{value}' if folder and '/' not in value else value)
    if folder and '/' in value and not requested.is_relative_to(base):
        raise VaultError('Dateipfad und genannter Ordner widersprechen sich.')
    if requested.is_file():
        return Resolution(to_relative(root, requested), [to_relative(root, requested)])
    explicit = '/' in value or bool(folder)
    # An explicit missing path never switches to a different folder.
    if explicit:
        md = requested.with_name(requested.name + '.md')
        if markdown and not requested.suffix and md.is_file():
            return Resolution(to_relative(root, md), [to_relative(root, md)])
        return Resolution(to_relative(root, requested if requested.suffix or not markdown else md), [])
    paths = list(iter_files(base))
    exact = [to_relative(root, p) for p in paths if p.name.casefold() == value.casefold()]
    if exact:
        return Resolution(exact[0], sorted(exact))
    stem = [to_relative(root, p) for p in paths if markdown and p.suffix.casefold() == '.md'
            and p.stem.casefold() == re.sub(r'\.md$', '', value, flags=re.I).casefold()]
    wanted = to_relative(root, requested if requested.suffix or not markdown else requested.with_name(requested.name + '.md'))
    return Resolution(stem[0] if len(stem) == 1 else wanted, sorted(stem))


def continue_file_action(prompt, pending):
    if not pending:
        return None
    match = re.fullmatch(rf'\s*(?:im\s+)?Ordner\s+(?P<folder>{REF})\s*[.!]?\s*', prompt, re.I)
    if match:
        return replace(FileAction(**pending), folder=unquote(match['folder']))
    if pending.get('action') == 'append' and pending.get('content') is None:
        match = re.fullmatch(r'\s*(?:Text|Inhalt):[ \t]*(?:\r?\n)?([\s\S]+)', prompt, re.I)
        if match:
            return replace(FileAction(**pending), content=match[1])
    return None


def execute_file_action(runner, plan: FileAction):
    started = time.perf_counter()
    root = runner.root
    resolution = resolve_file(root, plan.file, plan.folder, markdown=True)
    path = resolution.path
    if len(resolution.matches) > 1:
        return {'needs_input': True, 'message': 'Mehrere exakt passende Dateien: '
                + ', '.join(resolution.matches) + '. In welchem Ordner? Antworte mit „Ordner <Pfad>“.',
                'matches': resolution.matches, 'plan': asdict(plan)}
    if plan.action == 'find':
        return {'action': 'find', 'path': path, 'found': bool(resolution.matches),
                'message': f'Gefunden: [[{path}]]' if resolution.matches else f'Keine exakt passende Datei: {path}'}
    if plan.action in {'append', 'create'}:
        if not path.lower().endswith('.md'):
            raise VaultError('Textaktionen benötigen eine Markdown-Datei (.md).')
        if plan.action == 'append' and plan.content is None:
            return {'needs_input': True, 'message': f'Welchen Text soll ich zu [[{path}]] hinzufügen? Antworte mit „Text: …“.', 'plan': asdict(plan)}
        target = safe_join(root, path)
        exists = target.exists()
        if plan.action == 'create' and exists:
            return {'message': f'Die Datei [[{path}]] existiert bereits. Zum Ergänzen „Füge diesen Text … hinzu“ verwenden.', 'path': path}
        if plan.content is not None and not plan.content.strip():
            raise VaultError('Der anzuhängende Text ist leer.')
        # Read bytes with the existing encoding helper; never clean or summarize
        # user-supplied text, and never use semantic search to choose a target.
        from .vault import read_text_file, create_unique_file
        before = read_text_file(root, path)['content'] if exists else ''
        addition = plan.content if plan.content is not None else f'# {Path(path).stem}\n'
        separator = '' if not before or before.endswith('\n\n') else '\n' if before.endswith('\n') else '\n\n'
        content = before + separator + addition if plan.action == 'append' else addition
        approved_path, content = runner._review_note(path, content, create=not exists, literal=True)
        if approved_path != path:
            raise VaultError('Bei einer exakten Dateiaktion bleibt der angegebene Zielpfad verbindlich.')
        if exists:
            write_text_file(root, path, content, overwrite=True)
        else:
            create_unique_file(root, path, lambda out: out.write(content.encode('utf-8')), exact=True)
        runner._changed(path)
        verb = 'ergänzt' if exists else 'erstellt (exakter Zielpfad war nicht vorhanden)'
        return {'action': plan.action, 'path': path, 'ergaenzt' if exists else 'erstellt': path, 'message': f'[[{path}]] {verb}.',
                'elapsed_ms': round((time.perf_counter()-started)*1000, 2)}
    if not resolution.matches:
        return {'message': f'Datei nicht gefunden: {path}. Keine Änderung vorgenommen.', 'path': path}
    source = safe_join(root, path)
    if plan.action == 'delete':
        before_change(root, path)
        source.unlink()
        after_change(root, path)
        runner._changed(path)
        return {'action': 'delete', 'path': path, 'message': f'Datei gelöscht: {path}. Über „Rückgängig“ wiederherstellbar.'}
    if plan.action == 'rename':
        if '/' in plan.destination or plan.destination in {'.', '..'}:
            raise VaultError('Zum Umbenennen nur den neuen Dateinamen angeben; für Ordnerwechsel „Verschiebe“ verwenden.')
        name = plan.destination if Path(plan.destination).suffix else plan.destination + source.suffix
        destination = to_relative(root, source.parent / name)
    else:
        destination = (plan.destination.rstrip('/') + '/' + source.name).lstrip('/')
    target = safe_join(root, destination)
    if target.exists():
        raise VaultError(f'Ziel existiert bereits: {destination}. Keine Datei überschrieben.')
    from .tools import _outside_fences, _rewrite_links_after_moves, _build_link_resolver, _fix_links_in_line
    from .vault import read_text_file
    changes = []
    resolver = _build_link_resolver(root)
    mapping = {path.casefold(): destination}
    if source.suffix.lower() == '.md':
        mapping[path[:-3].casefold()] = destination
    # Short wikilinks are safe to rewrite only when the source is unique.
    if len(resolve_file(root, source.name).matches) == 1 and not (root / source.name).is_file():
        mapping[source.name.casefold()] = destination
        if source.suffix.lower() == '.md':
            mapping[source.stem.casefold()] = destination
    for note in iter_files(root, kinds=('note',)):
        relative = to_relative(root, note)
        original = read_text_file(root, relative)['content']
        stable = _outside_fences(original, lambda line: _fix_links_in_line(line, relative, resolver, [])) if relative == path else original
        updated = _outside_fences(stable, lambda line: _rewrite_links_after_moves(line, relative, mapping))
        if updated != original:
            changes.append((relative, updated))
    before_change(root, path)
    before_change(root, destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)
    after_change(root, path)
    after_change(root, destination)
    runner._changed(path)
    runner._changed(destination)
    for relative, content in changes:
        relative = destination if relative == path else relative
        write_text_file(root, relative, content, overwrite=True)
        runner._changed(relative)
    return {'action': plan.action, 'path': destination, 'message': f'[[{path}]] → [[{destination}]]. Links angepasst: {len(changes)}.'}
