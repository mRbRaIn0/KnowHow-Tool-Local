"""Resolve explicit Vault references without loading unrelated file contents."""
from dataclasses import dataclass
from pathlib import Path
import re

from .vault import VaultError, iter_files, kind_for, safe_join, to_relative


@dataclass(frozen=True)
class VaultFocus:
    # None means explicitly global; () means no existing Vault context requested.
    paths: tuple[str, ...] | None = ()
    ambiguous: tuple[str, ...] = ()

    def allows(self, path):
        value = path.replace('\\', '/').strip('/').casefold()
        return self.paths is None or any(
            value == target.rstrip('/').casefold()
            or (target.endswith('/') and value.startswith(target.casefold()))
            for target in self.paths)

    def files(self, root, kinds=None):
        if self.paths is None:
            yield from iter_files(root, kinds=kinds)
            return
        seen = set()
        for relative in self.paths:
            target = safe_join(root, relative)
            candidates = iter_files(target, kinds=kinds) if target.is_dir() else [target]
            for path in candidates:
                if path.is_file() and (not kinds or kind_for(path) in kinds) and path not in seen:
                    seen.add(path)
                    yield path

    def instruction(self):
        if self.ambiguous:
            return 'Ziel nicht eindeutig. Vollständigen Vault-Pfad erfragen: ' + '; '.join(self.ambiguous)
        if self.paths is None:
            return 'KONTEXTFOKUS: Der Nutzer hat den gesamten Vault ausdrücklich als Umfang gewählt.'
        if not self.paths:
            return ('KONTEXTFOKUS: Keine bestehenden Vault-Dateien oder Ordner erwähnt. '
                    'Arbeite mit den Nutzereingaben und aktuellen Anhängen. Keine allgemeine Vault-Erkundung. '
                    'Falls eine bestehende Zielnotiz nötig ist, erfrage nur deren Pfad.')
        return ('KONTEXTFOKUS: Nur diese genannten Ziele und ihre Unterdateien verwenden:\n- '
                + '\n- '.join(self.paths) + '\nAndere Themen und Ordner nicht einlesen. '
                'Dateien gezielt mit notiz_lesen lesen; bei naechster_offset weiterblättern. '
                'Alle relevanten Nutzerinformationen erhalten, fehlende Fakten als offen markieren.')


def resolve_focus(root: Path, prompt: str, global_default=False) -> VaultFocus:
    candidates = []
    explicit_dirs = set(re.findall(r'\b(?:Ordner|Verzeichnis)\s+["„`“]([^"„`“”\n]+)["“`”]', prompt, re.I))
    # WikiLinks, quoted paths (including spaces), and plain filenames/paths.
    for match in re.finditer(r'\[\[([^\]|#]+)(?:[^\]]*)\]\]|["„`“]([^"„`“”\n]+)["“`”]', prompt):
        candidates.append((match.group(1) or match.group(2)).strip())
    unquoted = re.sub(r'\[\[[^\]]+\]\]|["„`“][^"„`“”\n]+["“`”]', ' ', prompt)
    candidates.extend(re.findall(r'(?<![\w/\\])(?:[\w.-]+[/\\])*[\w.-]+\.(?:md|txt|pdf|docx|png|jpe?g|webp|csv)\b', unquoted, re.I))
    candidates.extend(re.findall(r'\b(?:Ordner|Verzeichnis)\s+([\w.-]+(?:[/\\][\w .-]+)*)', unquoted, re.I))
    candidates.extend(re.findall(r'(?<![\w/\\])(?:[\w.-]+[/\\])+[\w.-]+', unquoted))
    targets, unresolved = [], []
    for raw in dict.fromkeys(candidates):
        value = raw.replace('\\', '/').strip().strip('/').rstrip('.,;:')
        if not value or value in {'.', '..'} or '://' in raw:
            continue
        try:
            target = safe_join(root, value)
        except VaultError:
            continue
        if target.exists():
            targets.append(to_relative(root, target) + ('/' if target.is_dir() else ''))
        elif not target.suffix and target.with_suffix('.md').is_file():
            targets.append(to_relative(root, target.with_suffix('.md')))
        else:
            unresolved.append(value)
    ambiguous = []
    # Only a bare, unresolved name needs a metadata scan. Full paths/new targets do not.
    bare = [value for value in unresolved if '/' not in value]
    known = None
    if bare:
        known = list(iter_files(root))
    for value in unresolved:
        matches = set()
        if '/' not in value:
            exact_files = {to_relative(root, path) for path in known or []
                           if path.name.casefold() == value.casefold()}
            for path in known or []:
                if value.casefold() in {path.name.casefold(), path.stem.casefold()}:
                    matches.add(to_relative(root, path))
                for parent in path.parents:
                    if parent == root:
                        break
                    if parent.name.casefold() == value.casefold():
                        matches.add(to_relative(root, parent) + '/')
            if exact_files:
                matches = exact_files
        if len(matches) == 1:
            targets.extend(matches)
        elif len(matches) > 1:
            ambiguous.append(value + ' → ' + ', '.join(sorted(matches)))
        elif '/' in value or Path(value).suffix or value in explicit_dirs:
            targets.append(value + ('' if Path(value).suffix else '/'))
    targets = tuple(dict.fromkeys(targets))
    if targets or ambiguous:
        return VaultFocus(targets, tuple(ambiguous))
    global_request = bool(re.search(r'\bvaultweit\b|\b(?:ganzen?|gesamten?)\s+vault\b|\b(?:alle|allen|sämtliche|sämtlichen)\s+(?:(?:markdown|md)[ -]?)?(?:dateien|notizen|markdowns|mds)\b', prompt, re.I))
    return VaultFocus(None if global_request or global_default else ())
