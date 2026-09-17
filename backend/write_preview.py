"""Vorbereitete Notizinhalte; keine Mutation vor expliziter Übernahme."""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import re
import uuid


class PreviewNeeded(Exception):
    def __init__(self, path, before, after, create, expected):
        self.key = hashlib.sha256((path + '\0' + before + '\0' + after).encode()).hexdigest()
        self.expected = expected
        self.draft = {
            'id': uuid.uuid4().hex, 'path': path, 'before': before, 'after': after, 'create': create,
            'diff': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                               fromfile='Alt: ' + path, tofile='Neu: ' + path)),
            'sources': list(dict.fromkeys(re.findall(r'!?\[\[[^\]]+\]\]', after))),
        }


class PreviewCancelled(Exception):
    pass


pending: dict[tuple[str, str], dict] = {}


async def reviewed_call(runner, profile_id, chat_id, invoke):
    """Liefert Vorschauen und zuletzt das Ergebnis eines wiederholbaren Aufrufs."""
    while True:
        try:
            result = await invoke()
            yield {'result': result}
            return
        except PreviewNeeded as preview:
            future = asyncio.get_running_loop().create_future()
            key = (profile_id, chat_id)
            pending[key] = {'preview': preview, 'future': future}
            try:
                yield {'preview': preview.draft}
                decision = await future
            finally:
                pending.pop(key, None)
            if not decision['accept']:
                raise PreviewCancelled('Schreibvorschau abgebrochen. Keine weiteren Aktionen ausgeführt.')
            runner.approved_previews[preview.key] = {
                'path': decision.get('path') or preview.draft['path'],
                'content': decision.get('content') if decision.get('content') is not None else preview.draft['after'],
                'expected': preview.expected,
                'original_path': preview.draft['path'],
            }
