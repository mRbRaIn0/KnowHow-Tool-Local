"""Chat: Verläufe verwalten und Antworten von Ollama streamen."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..deps import current_db, current_ollama, current_profile
from ..ollama_client import OllamaError
from .. import attachments
from ..note_templates import list_templates, select_template, template_instruction
from ..knowledge import context_for_prompt, hybrid_search
from ..tools import (
    ATTACHMENT_TOOLS, BASE_INSTRUCTIONS, EDIT_TOOLS, TOOL_DEFINITIONS, WRITING_TOOLS,
    ToolRunner, canonical_tool_name, clean_generated_text, vault_overview,
)
from ..vault import IMAGE_EXT, VaultError, require_root
from ..vault_guide import ensure_vault_guide, guide_context
from ..workflow import analyse_request

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chat"])

MAX_TITLE_LENGTH = 60
MAX_FOLDER_NAME = 60

# Werkzeugrunden je Antwort. Wer 50 Dateien anhängt, braucht auch 50+ Runden;
# die Obergrenze verhindert nur Endlosschleifen.
BASE_TOOL_ROUNDS = 18
MAX_TOOL_ROUNDS = 120

# Vorauswertung von Anhängen: ausführlich bei wenigen, knapper bei vielen.
AUSFUEHRLICH_BIS = 5
BESCHREIBUNG_LANG = 8000
BESCHREIBUNG_KURZ = 900
KONTEXT_JE_ANHANG = 7000


def _tool_rounds(anzahl_anhaenge: int) -> int:
    """Genug Runden, um jeden Anhang zu lesen und danach noch zu schreiben."""
    return min(MAX_TOOL_ROUNDS, BASE_TOOL_ROUNDS + anzahl_anhaenge * 2)


class ChatCreate(BaseModel):
    title: str = "Neuer Chat"
    purpose: Literal["vault", "ask"] = "vault"
    folder_id: str = ""


class ChatUpdate(BaseModel):
    """Alle Felder optional: gesetzt wird nur, was mitgeschickt wurde."""
    title: Optional[str] = None
    folder_id: Optional[str] = None   # "" verschiebt zurück auf die oberste Ebene
    archived: Optional[bool] = None


class FolderCreate(BaseModel):
    name: str = "Neuer Ordner"
    purpose: Literal["vault", "ask"] = "vault"


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    collapsed: Optional[bool] = None
    position: Optional[int] = None


class Attachment(BaseModel):
    """Anhang einer Nachricht: Bild (base64) oder Vault-Datei als Textkontext."""
    kind: str = "image"           # image | file
    name: str = ""
    path: str = ""               # vault-relativ, falls aus dem Vault
    data: str = ""               # base64 ohne Data-URL-Präfix (nur Bilder)
    text: str = ""               # extrahierter Text (Dokumente)


class MessageRequest(BaseModel):
    content: str = ""
    attachments: List[Attachment] = Field(default_factory=list)
    model: Optional[str] = None
    use_rag: bool = True


@router.get("")
async def list_chats(search: str = "", limit: int = 200,
                     purpose: Optional[Literal["vault", "ask"]] = None) -> Dict[str, Any]:
    return {
        "chats": current_db().list_chats(
            limit=limit, search=search, purpose=purpose or ""
        )
    }


@router.post("")
async def create_chat(request: ChatCreate) -> Dict[str, Any]:
    profile = current_profile()
    return current_db(profile).create_chat(
        request.title, profile.ollama.chat_model, request.purpose, request.folder_id
    )


# Die Ordner-Routen müssen vor "/{chat_id}" stehen, sonst schluckt der
# Platzhalter das Wort "folders".

@router.get("/folders")
async def list_folders(purpose: Optional[Literal["vault", "ask"]] = None) -> Dict[str, Any]:
    return {"folders": current_db().list_folders(purpose or "")}


@router.post("/folders")
async def create_folder(request: FolderCreate) -> Dict[str, Any]:
    name = request.name.strip()[:MAX_FOLDER_NAME] or "Neuer Ordner"
    return current_db().create_folder(name, request.purpose)


@router.patch("/folders/{folder_id}")
async def update_folder(folder_id: str, request: FolderUpdate) -> Dict[str, Any]:
    database = current_db()
    if not database.get_folder(folder_id):
        raise HTTPException(404, {"message": "Ordner nicht gefunden.", "kind": "not_found"})
    name = None
    if request.name is not None:
        name = request.name.strip()[:MAX_FOLDER_NAME] or "Neuer Ordner"
    database.update_folder(folder_id, name=name, collapsed=request.collapsed,
                           position=request.position)
    return database.get_folder(folder_id)


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str) -> Dict[str, Any]:
    """Löscht den Ordner; enthaltene Chats bleiben erhalten."""
    current_db().delete_folder(folder_id)
    return {"deleted": True, "id": folder_id}


@router.get("/{chat_id}")
async def get_chat(chat_id: str) -> Dict[str, Any]:
    database = current_db()
    chat = database.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, {"message": "Chat nicht gefunden.", "kind": "not_found"})
    return {"chat": chat, "messages": database.list_messages(chat_id)}


@router.patch("/{chat_id}")
async def update_chat(chat_id: str, request: ChatUpdate) -> Dict[str, Any]:
    database = current_db()
    if not database.get_chat(chat_id):
        raise HTTPException(404, {"message": "Chat nicht gefunden.", "kind": "not_found"})
    if request.title is not None:
        database.rename_chat(chat_id, request.title.strip()[:200] or "Neuer Chat")
    if request.folder_id is not None:
        database.move_chat(chat_id, request.folder_id)
    if request.archived is not None:
        database.set_chat_archived(chat_id, request.archived)
    return database.get_chat(chat_id)


@router.delete("/{chat_id}")
async def delete_chat(chat_id: str) -> Dict[str, Any]:
    """Löscht Verlauf **und** Zwischenablage.

    Die hochgeladenen Originale und ihr ausgewerteter Klartext liegen unter
    data/uploads/<chat_id>. Ohne diesen Schritt blieben Kundendokumente nach
    dem Löschen des Chats auf der Platte liegen — ein Löschauftrag muss
    vollständig sein. Die Prüfung auf das aktive Profil verhindert zugleich,
    dass ein fremder Chat mitgelöscht wird.
    """
    database = current_db()
    if not database.get_chat(chat_id):
        raise HTTPException(404, {"message": "Chat nicht gefunden.", "kind": "not_found"})
    database.delete_chat(chat_id)
    await asyncio.to_thread(attachments.clear, chat_id)
    return {"deleted": True, "id": chat_id}


@router.delete("/{chat_id}/messages/{message_id}")
async def delete_message(chat_id: str, message_id: int) -> Dict[str, Any]:
    current_db().delete_message(message_id)
    return {"deleted": True, "id": message_id}


@router.post("/{chat_id}/message")
async def send_message(chat_id: str, request: MessageRequest) -> StreamingResponse:
    """Nimmt eine Nachricht entgegen und streamt die Modellantwort als SSE."""
    profile = current_profile()
    database = current_db(profile)
    chat = database.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, {"message": "Chat nicht gefunden.", "kind": "not_found"})
    question_mode = chat.get("purpose") == "ask"
    if not request.content.strip() and not request.attachments:
        raise HTTPException(400, {"message": "Die Nachricht ist leer.", "kind": "empty"})
    if question_mode and request.attachments:
        raise HTTPException(400, {
            "message": (
                "Anhänge gehören in ‚Wissen erweitern‘. Der Fragen-Chat liest "
                "ausschließlich aus der freigegebenen Wissensbasis."
            ),
            "kind": "wrong_chat_mode",
        })

    model = request.model or profile.ollama.chat_model
    client = current_ollama(profile)

    # Der Vault steht auch bei Modellen ohne Tool-Calling für das deterministische
    # Schreib-Sicherheitsnetz bereit. Werkzeugdefinitionen bekommt das Modell
    # weiterhin nur, wenn es sie laut Ollama wirklich unterstützt.
    capabilities = await client.capabilities(model)
    root: Optional[Path] = None
    try:
        root = require_root(profile.vault_path)
    except VaultError:
        root = None
    vault_guide = ""
    if root is not None and not question_mode:
        try:
            await asyncio.to_thread(ensure_vault_guide, root, True)
            vault_guide = await asyncio.to_thread(guide_context, root)
        except OSError as exc:
            log.warning("00 Inhalt konnte nicht geladen werden: %s", exc)
    # Nur die noch nicht verarbeiteten Anhänge gehören zu dieser Eingabe.
    # Früher angehängte Dateien bleiben über die Werkzeuge erreichbar, sobald
    # sie ausdrücklich erwähnt werden — sie drängen sich aber nicht mehr auf.
    vorhandene_anhaenge = (
        [] if question_mode
        else await asyncio.to_thread(attachments.pending, chat_id)
    )
    alle_anhaenge = (
        [] if question_mode
        else await asyncio.to_thread(attachments.listing, chat_id)
    )
    prior_user_messages = [
        item["content"] for item in database.list_messages(chat_id)
        if item.get("role") == "user" and item.get("content", "").strip()
    ]
    requirements = analyse_request(
        request.content,
        (item["name"] for item in vorhandene_anhaenge),
        prior_user_messages,
    )
    selected_template = None
    if root is not None and not question_mode and requirements.note_write:
        available = await asyncio.to_thread(
            list_templates, root, profile.vault.templates_dir
        )
        selected_template = select_template(request.content, available)

    async def vision(prompt: str, image_b64: str) -> str:
        """Ein einzelnes Bild ansehen — eigener Aufruf, damit auch viele
        Bilder nacheinander verarbeitet werden können, ohne den Kontext zu sprengen."""
        teile: List[str] = []
        async for chunk in client.chat_stream(
            model,
            [{"role": "user", "content": prompt, "images": [image_b64]}],
            options={"temperature": 0.2, "num_ctx": profile.ai.num_ctx},
            think=False if "thinking" in capabilities else None,
        ):
            teil = (chunk.get("message") or {}).get("content")
            if teil:
                teile.append(teil)
            if chunk.get("done"):
                break
        return "".join(teile).strip() or "(keine Beschreibung erhalten)"

    runner = ToolRunner(
        root,
        chat_id=chat_id,
        attachment_dir=profile.vault.attachments_dir,
        vision=vision if "vision" in capabilities else None,
        allow_edit=requirements.requires_edit,
        allow_full_rewrite=requirements.allow_full_rewrite,
        batch_edit_operations=requirements.batch_edit_operations,
        allow_file_organization=requirements.organize_vault_files,
    ) if root and not question_mode else None

    tools = None
    if runner and "tools" in capabilities:
        tools = list(TOOL_DEFINITIONS)
        if requirements.requires_edit or requirements.organize_vault_files:
            tools += [
                tool for tool in EDIT_TOOLS
                if (
                    (tool["function"]["name"] == "notiz_bearbeiten"
                     and requirements.requires_edit)
                    or (tool["function"]["name"] == "markdown_dateien_bereinigen"
                        and requirements.requires_batch_edit)
                    or (tool["function"]["name"] == "dateien_in_unterordner_verschieben"
                        and requirements.organize_vault_files)
                )
            ]
        if alle_anhaenge:
            anhang_werkzeuge = list(ATTACHMENT_TOOLS)
            if requirements.keep_out_of_vault:
                # Ausdrücklich "nur ansehen": Das Ablegen wird gar nicht erst
                # angeboten, damit es auch nicht versehentlich passieren kann.
                anhang_werkzeuge = [
                    werkzeug for werkzeug in anhang_werkzeuge
                    if werkzeug["function"]["name"] != "anhang_in_vault_ablegen"
                ]
            tools += anhang_werkzeuge

    # Die Anhänge dieser Eingabe werden an der Nachricht festgehalten. Dadurch
    # bleibt im Verlauf sichtbar, welche Datei zu welcher Frage gehörte, auch
    # wenn sie für die nächste Eingabe nicht mehr aktiv ist.
    nachrichten_anhaenge = [] if question_mode else (
        [
            {"kind": item["kind"], "name": item["name"], "size": item["size"]}
            for item in vorhandene_anhaenge
        ] or [a.model_dump() for a in request.attachments]
    )
    user_message = database.add_message(
        chat_id, "user", request.content, attachments=nachrichten_anhaenge, model=model
    )

    # Ersten Nutzertext als Chattitel übernehmen, solange noch keiner gesetzt ist.
    if chat["title"] in ("", "Neuer Chat", "Neuer Wissens-Chat", "Neue Frage") \
            and request.content.strip():
        database.rename_chat(chat_id, _title_from(request.content))

    if question_mode:
        system_prompt = _question_system_prompt(profile.ai.system_prompt)
    else:
        overview = await asyncio.to_thread(vault_overview, root) if root else ""
        system_prompt = _system_prompt(
            profile.ai.system_prompt,
            root,
            overview,
            vault_guide,
            "\n\n".join(filter(None, (
                requirements.contract(), template_instruction(selected_template)
            ))),
        )
    # Kein Hinweistext mehr noetig: Die Inhalte werden unten vorab ausgewertet
    # und direkt in den Verlauf gestellt.
    history = _build_history(database, chat_id, system_prompt)
    # Ausgewertete Anhänge brauchen Platz im Kontextfenster.
    num_ctx = profile.ai.num_ctx
    if vorhandene_anhaenge:
        num_ctx = max(num_ctx, min(32768, 4096 + len(vorhandene_anhaenge) * 1400))
    options = {
        "temperature": profile.ai.temperature,
        "num_ctx": num_ctx,
        # Genug Ausgabetokens für Denken, Werkzeugentscheidung und eine wirklich
        # vollständige Antwort. Die Abschlussprüfung unten setzt bei einem
        # Längenstopp trotzdem automatisch fort.
        "num_predict": max(2048, min(8192, num_ctx // 2)),
    }

    # Thinking nur setzen, wenn das Modell es kann. Ohne ausdrückliches False
    # denken Modelle wie qwen3.5 bei jeder Antwort — das kostet spürbar Zeit.
    think = (
        bool(profile.ai.thinking or (requirements.actionable and not question_mode))
        if "thinking" in capabilities else None
    )
    rundenlimit = _tool_rounds(len(vorhandene_anhaenge))

    async def event_stream():
        yield _sse({"type": "user_message", "message": user_message})

        rag_result: Dict[str, Any] = {}
        use_knowledge = question_mode or request.use_rag
        if root is not None and use_knowledge \
                and len(request.content.strip()) >= 2:
            yield _sse({"type": "knowledge_progress", "message": "Freigegebenes Wissen wird durchsucht …"})
            try:
                rag_result = await hybrid_search(
                    root, database, request.content, client,
                    profile.ollama.embed_model, profile.ai.rag_top_k,
                    excluded_dirs=(profile.vault.templates_dir,),
                    refresh=question_mode,
                )
                rag_context = context_for_prompt(rag_result)
                if rag_context:
                    _append_to_latest_user(history, rag_context)
                yield _sse({
                    "type": "knowledge_ready",
                    "sources": len(rag_result.get("results") or []),
                    "semantic": rag_result.get("semantic", False),
                })
            except Exception as exc:
                # RAG ist eine Qualitätsverbesserung; Chat und Werkzeugzugriff
                # müssen bei einem kaputten Dokument oder fehlenden Modell laufen.
                log.warning("Wissenssuche fehlgeschlagen: %s", exc)
                yield _sse({"type": "knowledge_ready", "sources": 0, "semantic": False})

        # Anhänge zuerst auswerten — erst danach antwortet das Modell.
        if vorhandene_anhaenge:
            auswertung = {}
            async for meldung in _auswerten(
                chat_id, vorhandene_anhaenge, request.content,
                vision if "vision" in capabilities else None, runner,
            ):
                if "fortschritt" in meldung:
                    yield _sse({"type": "attachment_progress", **meldung["fortschritt"]})
                elif meldung.get("fertig"):
                    auswertung = meldung["cache"]
            kontext = _anhang_kontext(vorhandene_anhaenge, auswertung)
            if kontext:
                for eintrag in reversed(history):
                    if eintrag["role"] == "user":
                        eintrag["content"] = f"{eintrag['content']}\n\n{kontext}"
                        break
            # Ab jetzt gelten sie als verarbeitet: Die nächste Eingabe startet
            # wieder ohne Anhänge, ohne dass etwas gelöscht wird.
            await asyncio.to_thread(
                attachments.mark_used, chat_id,
                [item["name"] for item in vorhandene_anhaenge],
            )
            yield _sse({
                "type": "attachments_ready",
                "anzahl": len(vorhandene_anhaenge),
                "abgelegt": not requirements.keep_out_of_vault,
            })

        assistant = database.add_message(chat_id, "assistant", "", model=model)
        yield _sse({"type": "start", "message_id": assistant["id"], "model": model})

        content_parts: List[str] = []
        thinking_parts: List[str] = []
        steps: List[dict] = []
        saved = False
        completed = False
        correction_rounds = 0
        last_draft = ""
        limit_reached = False

        if rag_result.get("results"):
            rag_step = {
                "tool": "wissenssuche",
                "arguments": {"query": request.content},
                "result": {
                    "anzahl": len(rag_result["results"]),
                    "semantisch": rag_result.get("semantic", False),
                    "quellen": [
                        {"pfad": item["path"], "seite": item.get("page", 0)}
                        for item in rag_result["results"]
                    ],
                },
                "writing": False,
                "ok": True,
            }
            steps.append(rag_step)
            yield _sse({"type": "tool_result", **rag_step})

        def persist() -> str:
            """Zwischenstand sichern. Auch bei Abbruch geht kein Text verloren."""
            nonlocal saved
            text = "".join(content_parts)
            if not saved:
                database.update_message(assistant["id"], content=text,
                                        thinking="".join(thinking_parts), sources=steps)
                database.touch_chat(chat_id, model)
                saved = True
            return text

        try:
            # Eindeutige vaultweite Mechanik wird sofort und deterministisch
            # ausgeführt. Das lokale Modell darf daraus keine lange Absichts-
            # erklärung machen oder die vorhandene Dateisystemfunktion leugnen.
            if (runner is not None
                    and (requirements.requires_batch_edit
                         or requirements.organize_vault_files)
                    and not requirements.archive_attachments):
                automatic = await asyncio.to_thread(
                    runner.finish_required_actions,
                    requirements,
                    request.content,
                    "",
                )
                for step in automatic:
                    steps.append(step)
                    yield _sse({"type": "tool_result", **step})
                remaining = runner.missing_actions(requirements)
                if not remaining:
                    final_round = _special_operation_confirmation(steps)
                    content_parts.append(final_round)
                    yield _sse({"type": "content", "delta": final_round})
                    completed = True
                    content = persist()
                    yield _sse({
                        "type": "done",
                        "message_id": assistant["id"],
                        "content": content,
                        "steps": steps,
                        "changed_files": runner.changed_files,
                    })
                    return

            for round_number in range(rundenlimit):
                tool_calls: List[dict] = []
                round_content: List[str] = []
                round_done_reason = ""

                async for chunk in client.chat_stream(
                    model, history, options=options, think=think, tools=tools
                ):
                    message = chunk.get("message") or {}
                    thinking = message.get("thinking")
                    if thinking:
                        thinking_parts.append(thinking)
                        yield _sse({"type": "thinking", "delta": thinking})
                    delta = message.get("content")
                    if delta:
                        round_content.append(delta)
                        # Bei eindeutigen Schreibaufträgen ist ein Text zunächst
                        # nur ein Entwurf. Sichtbar und gespeichert wird er erst,
                        # wenn die verlangten Vault-Aktionen nachweislich erfolgt
                        # sind oder das Sicherheitsnetz sie ausgeführt hat.
                        if not requirements.actionable or runner is None:
                            content_parts.append(delta)
                            yield _sse({"type": "content", "delta": delta})
                    for call in message.get("tool_calls") or []:
                        tool_calls.append(call)
                    if chunk.get("done"):
                        round_done_reason = str(chunk.get("done_reason") or "")
                        break

                if not tool_calls or runner is None:
                    draft = "".join(round_content).strip()
                    if draft:
                        last_draft = draft

                    if runner is not None and requirements.actionable:
                        automatic: List[dict] = []
                        missing = runner.missing_actions(requirements)
                        if missing and tools and correction_rounds < 2:
                            correction_rounds += 1
                            history.append({"role": "assistant", "content": draft})
                            history.append({
                                "role": "system",
                                "content": requirements.correction(missing),
                            })
                            log.info(
                                "Korrigiere unvollständigen Vault-Auftrag in Chat %s: %s",
                                chat_id, ", ".join(missing),
                            )
                            continue

                        if missing:
                            automatic = await asyncio.to_thread(
                                runner.finish_required_actions,
                                requirements,
                                request.content,
                                last_draft,
                            )
                            for step in automatic:
                                steps.append(step)
                                yield _sse({"type": "tool_result", **step})

                        remaining = runner.missing_actions(requirements)
                        if (not remaining
                                and _response_needs_continuation(draft, round_done_reason)
                                and correction_rounds < 3):
                            correction_rounds += 1
                            history.append({"role": "assistant", "content": draft})
                            history.append({
                                "role": "system",
                                "content": _continuation_instruction(round_done_reason),
                            })
                            continue
                        batch_completed = any(
                            step.get("tool") == "markdown_dateien_bereinigen"
                            and step.get("ok")
                            and isinstance(step.get("result"), dict)
                            and step["result"].get("vollstaendig") is True
                            for step in steps
                        )
                        # Bei globalen Dateioperationen stammen Umfang und Ergebnis
                        # vollständig aus dem deterministischen Batch-Werkzeug. Eine
                        # frei formulierte Modellzusammenfassung kann dagegen
                        # abbrechen oder den geprüften Umfang falsch beschreiben.
                        organization_completed = any(
                            step.get("tool") == "dateien_in_unterordner_verschieben"
                            and step.get("ok")
                            and isinstance(step.get("result"), dict)
                            and step["result"].get("vollstaendig") is True
                            for step in steps
                        )
                        if ((batch_completed or organization_completed)
                                and not remaining):
                            final_round = _special_operation_confirmation(steps)
                        else:
                            final_round = clean_generated_text(draft)
                            if not final_round:
                                final_round = _change_confirmation(runner.changed_files)
                        if automatic and not (batch_completed or organization_completed):
                            confirmation = (
                                _incomplete_confirmation(remaining)
                                if remaining else _change_confirmation(runner.changed_files)
                            )
                            final_round = (
                                final_round.rstrip()
                                + "\n\n"
                                + confirmation
                            ).strip()
                        if final_round:
                            content_parts.append(final_round)
                            yield _sse({"type": "content", "delta": final_round})
                    elif _response_needs_continuation(draft, round_done_reason):
                        if correction_rounds < 3:
                            correction_rounds += 1
                            history.append({"role": "assistant", "content": draft})
                            history.append({
                                "role": "system",
                                "content": _continuation_instruction(round_done_reason),
                            })
                            if content_parts:
                                content_parts.append("\n\n")
                                yield _sse({"type": "content", "delta": "\n\n"})
                            log.info(
                                "Setze unvollständige Antwort in Chat %s fort (%d/3)",
                                chat_id, correction_rounds,
                            )
                            continue
                    break

                # Der Aufruf des Modells gehört in den Verlauf, sonst fehlt der
                # Bezug für die Werkzeugantwort.
                history.append({
                    "role": "assistant",
                    "content": "".join(round_content),
                    "tool_calls": tool_calls,
                })

                for call in tool_calls:
                    function = call.get("function") or {}
                    name = canonical_tool_name(function.get("name", ""))
                    arguments = function.get("arguments") or {}
                    yield _sse({"type": "tool_start", "tool": name, "arguments": arguments})

                    result = await runner.run(name, arguments)
                    step = {
                        "tool": name,
                        "arguments": arguments,
                        "result": result,
                        "writing": name in WRITING_TOOLS,
                        "ok": "fehler" not in result,
                    }
                    steps.append(step)
                    yield _sse({"type": "tool_result", **step})

                    history.append({
                        "role": "tool",
                        "tool_name": name,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                if round_number == rundenlimit - 1:
                    # Auch der Werkzeugaufruf der letzten erlaubten Runde wird
                    # ausgeführt. Danach übernimmt ein kontrollierter Abschluss,
                    # statt den Nutzer zum erneuten Nachfragen zu zwingen.
                    limit_reached = True
                    log.info("Werkzeuggrenze erreicht (%d Runden) in Chat %s",
                             rundenlimit, chat_id)
                    break

            if limit_reached:
                if runner is not None and requirements.actionable:
                    automatic = await asyncio.to_thread(
                        runner.finish_required_actions,
                        requirements,
                        request.content,
                        last_draft,
                    )
                    for step in automatic:
                        steps.append(step)
                        yield _sse({"type": "tool_result", **step})
                    remaining = runner.missing_actions(requirements)
                    final_round = (
                        _incomplete_confirmation(remaining)
                        if remaining else _special_operation_confirmation(steps)
                    )
                    if not final_round.strip():
                        final_round = _change_confirmation(runner.changed_files)
                    content_parts.append(final_round)
                    yield _sse({"type": "content", "delta": final_round})
                else:
                    if content_parts:
                        content_parts.append("\n\n")
                        yield _sse({"type": "content", "delta": "\n\n"})
                    history.append({
                        "role": "system",
                        "content": (
                            "Die Werkzeugphase ist beendet. Nutze keine weiteren "
                            "Werkzeuge. Formuliere jetzt aus den bereits erhaltenen "
                            "Ergebnissen eine vollständige direkte Antwort auf den "
                            "Nutzerauftrag. Keine Ankündigung weiterer Arbeit."
                        ),
                    })
                    for final_attempt in range(3):
                        final_parts: List[str] = []
                        final_reason = ""
                        async for chunk in client.chat_stream(
                            model, history, options=options, think=think, tools=None
                        ):
                            message = chunk.get("message") or {}
                            thinking = message.get("thinking")
                            if thinking:
                                thinking_parts.append(thinking)
                                yield _sse({"type": "thinking", "delta": thinking})
                            delta = message.get("content")
                            if delta:
                                final_parts.append(delta)
                                content_parts.append(delta)
                                yield _sse({"type": "content", "delta": delta})
                            if chunk.get("done"):
                                final_reason = str(chunk.get("done_reason") or "")
                                break
                        final_text = "".join(final_parts).strip()
                        if not _response_needs_continuation(final_text, final_reason):
                            break
                        history.append({"role": "assistant", "content": final_text})
                        history.append({
                            "role": "system",
                            "content": _continuation_instruction(final_reason),
                        })
                        content_parts.append("\n\n")
                        yield _sse({"type": "content", "delta": "\n\n"})

            # Auch bei frei formulierten Aufträgen gilt: Wenn das Modell eine
            # Notiz und Anhänge geschrieben hat, darf kein echter Link fehlen.
            if runner is not None:
                linked = await asyncio.to_thread(runner.ensure_attachment_links)
                if linked:
                    step = {
                        "tool": "dateien_verknuepfen", "arguments": {},
                        "result": linked, "writing": True, "ok": True,
                        "automatic": True,
                    }
                    steps.append(step)
                    yield _sse({"type": "tool_result", **step})
            completed = True
        except OllamaError as exc:
            persist()
            yield _sse({"type": "error", "message": exc.message, "kind": exc.kind})
            return
        except Exception as exc:  # defensiv: Stream darf die App nie abstürzen lassen
            log.exception("Unerwarteter Fehler im Chatstream")
            persist()
            yield _sse({"type": "error", "message": f"Unerwarteter Fehler: {exc}", "kind": "error"})
            return
        finally:
            # Greift nur bei echtem Abbruch — etwa wenn der Browser die
            # Verbindung trennt (Neuladen, Fenster geschlossen).
            if not completed and not saved and (content_parts or thinking_parts):
                persist()
                log.info("Chatstream abgebrochen — Zwischenstand gesichert (%d Zeichen).",
                         len("".join(content_parts)))

        content = persist()
        yield _sse({
            "type": "done",
            "message_id": assistant["id"],
            "content": content,
            "steps": steps,
            "changed_files": runner.changed_files if runner else [],
        })

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _auswerten(chat_id: str, items: List[dict], frage: str,
                     vision, runner) -> AsyncIterator[dict]:
    """Wertet alle Anhänge aus, bevor das Modell antwortet.

    Ob ein Modell von sich aus zum Bild greift, ist nicht verlässlich — bei
    vielen Anhängen behauptet es gerne, sie zu sehen, und erfindet den Inhalt.
    Deshalb werden die Inhalte hier bereitgestellt, statt darauf zu hoffen.

    Liefert Fortschrittsmeldungen; das Ergebnis steht danach in `cache`.
    """
    cache = await asyncio.to_thread(attachments.load_cache, chat_id)
    offen = [item for item in items if item["name"] not in cache]
    if not offen:
        yield {"fertig": True, "cache": cache}
        return

    grenze = BESCHREIBUNG_LANG if len(offen) <= AUSFUEHRLICH_BIS else BESCHREIBUNG_KURZ
    auftrag = (
        "Beschreibe genau, was hier zu sehen ist. Gib ALLEN erkennbaren Text "
        "wörtlich wieder, auch Kennungen, Codes und Zahlen. Tabellen als Markdown. "
        "Erfinde nichts."
    )
    if frage.strip():
        auftrag += f"\n\nDer Nutzer möchte wissen: {frage.strip()[:300]}"

    for nummer, item in enumerate(offen, start=1):
        name = item["name"]
        yield {"fortschritt": {"name": name, "nummer": nummer, "gesamt": len(offen),
                               "kind": item["kind"]}}
        try:
            path = await asyncio.to_thread(attachments.resolve, chat_id, name)
            endung = path.suffix.lower()

            if endung in IMAGE_EXT and vision is not None:
                daten = await asyncio.to_thread(attachments.image_base64, path)
                text = (await vision(auftrag, daten))[:grenze]

            elif endung == ".pdf":
                gelesen = await asyncio.to_thread(attachments.extract_text, path)
                if gelesen.get("text"):
                    text = gelesen["text"][:grenze]
                elif vision is not None:
                    # Scan ohne Textebene: Seiten als Bild auswerten.
                    seiten = await asyncio.to_thread(attachments.pdf_page_images, path)
                    teile = []
                    for index, seite in enumerate(seiten, start=1):
                        teile.append(f"--- Seite {index} ---\n{await vision(auftrag, seite)}")
                    text = "\n\n".join(teile)[:grenze * 2]
                else:
                    text = gelesen.get("hinweis", "")

            else:
                gelesen = await asyncio.to_thread(attachments.extract_text, path)
                text = (gelesen.get("text") or gelesen.get("hinweis")
                        or gelesen.get("fehler") or "")[:grenze]

            cache[name] = text or "(kein Inhalt erkennbar)"
        except Exception as exc:  # eine kaputte Datei darf nichts abbrechen
            log.warning("Anhang %s konnte nicht ausgewertet werden: %s", name, exc)
            cache[name] = f"(konnte nicht ausgewertet werden: {exc})"

    await asyncio.to_thread(attachments.save_cache, chat_id, cache)
    yield {"fertig": True, "cache": cache}


def _anhang_kontext(items: List[dict], cache: dict) -> str:
    """Baut den Textblock mit den ausgewerteten Inhalten."""
    if not items:
        return ""
    je_anhang = max(400, min(KONTEXT_JE_ANHANG, 26000 // max(1, len(items))))
    bloecke = []
    for item in items:
        inhalt = (cache.get(item["name"]) or "").strip()
        if not inhalt:
            continue
        if len(inhalt) > je_anhang:
            inhalt = inhalt[:je_anhang] + " […]"
        bloecke.append(f'### Anhang: {item["name"]}\n{inhalt}')

    if not bloecke:
        return ""
    return (
        "INHALT DER ANGEHÄNGTEN DATEIEN (bereits ausgewertet, verlässlich):\n\n"
        + "\n\n".join(bloecke)
        + "\n\nNutze diese Inhalte als konkrete fachliche Quellen und erfinde keine Werte. "
          "Schreibe keinen pauschalen Metasatz über die Herkunft der Notiz. "
          "Brauchst du zu einer Datei mehr Details, nutze bild_ansehen oder anhang_lesen."
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _title_from(text: str) -> str:
    title = " ".join(text.strip().split())
    if len(title) > MAX_TITLE_LENGTH:
        title = title[:MAX_TITLE_LENGTH].rsplit(" ", 1)[0] + "…"
    return title or "Neuer Chat"


def _change_confirmation(paths: List[str]) -> str:
    if not paths:
        return "Der angeforderte Vault-Auftrag konnte nicht vollständig ausgeführt werden."
    if len(paths) == 1:
        return f"Im Vault gespeichert: `{paths[0]}`"
    return "Im Vault gespeichert:\n" + "\n".join(f"- `{path}`" for path in paths)


def _batch_confirmation(steps: List[dict]) -> str:
    """Erzeugt eine vollständige, faktenbasierte Zusammenfassung des Batch-Laufs."""
    result: Dict[str, Any] = {}
    for step in reversed(steps):
        if step.get("tool") == "markdown_dateien_bereinigen" and step.get("ok"):
            candidate = step.get("result")
            if isinstance(candidate, dict):
                result = candidate
                break

    if not result:
        return "Der globale Vault-Auftrag wurde ausgeführt."

    operations = result.get("operationen") or []
    operation_labels = []
    if "remove_emojis" in operations:
        operation_labels.append("Emojis entfernt")
    if "fix_relative_links" in operations:
        operation_labels.append(
            "relative Links und Ordner-WikiLinks auf vorhandene Notizen normalisiert"
        )

    checked = int(result.get("geprueft") or 0)
    changed = int(result.get("geaendert") or 0)
    unchanged = int(result.get("unveraendert") or 0)
    lines = [
        f"Fertig. Alle {checked} Markdown-Dateien im Vault wurden geprüft.",
        "",
        f"- Geändert: {changed}",
        f"- Unverändert: {unchanged}",
    ]
    if operation_labels:
        lines.append(f"- Ausgeführt: {'; '.join(operation_labels)}")

    paths = result.get("geaenderte_dateien") or []
    if paths:
        lines.extend(["", "Bearbeitete Dateien:"])
        lines.extend(f"- `{path}`" for path in paths)

    unresolved = result.get("nicht_aufloesbare_links") or []
    lines.extend(["", f"Nicht auflösbare Links: {len(unresolved)}"])
    if unresolved:
        lines.extend(f"- `{item}`" for item in unresolved)
    return "\n".join(lines)


def _organization_confirmation(steps: List[dict]) -> str:
    """Fasst eine tatsächlich ausgeführte Dateiordnung ohne Modellannahmen zusammen."""
    result: Dict[str, Any] = {}
    for step in reversed(steps):
        if (step.get("tool") == "dateien_in_unterordner_verschieben"
                and step.get("ok") and isinstance(step.get("result"), dict)):
            result = step["result"]
            break
    if not result:
        return ""

    checked = int(result.get("geprueft") or 0)
    moved = int(result.get("verschoben_anzahl") or 0)
    already = int(result.get("bereits_eingeordnet") or 0)
    folder = str(result.get("unterordner") or "Dateien")
    changed_notes = result.get("geaenderte_notizen") or []
    lines = [
        f"Fertig. {checked} PDF-, Dokument- und Bilddateien wurden geprüft.",
        "",
        f"- In den Unterordner `{folder}` verschoben: {moved}",
        f"- Bereits passend eingeordnet: {already}",
        f"- Notizen mit aktualisierten Links: {len(changed_notes)}",
    ]
    moved_items = result.get("verschoben") or []
    if moved_items:
        lines.extend(["", "Neue Vault-Pfade:"])
        lines.extend(
            f"- `{item.get('alter_pfad', '')}` → `{item.get('neuer_pfad', '')}`"
            for item in moved_items
        )
    guide = result.get("hauptseite") or {}
    if guide.get("updated"):
        lines.extend([
            "",
            f"Die dauerhafte Ablageregel wurde außerdem in `{guide.get('path')}` ergänzt.",
        ])
    return "\n".join(lines)


def _special_operation_confirmation(steps: List[dict]) -> str:
    parts = []
    organization = _organization_confirmation(steps)
    if organization:
        parts.append(organization)
    if any(step.get("tool") == "markdown_dateien_bereinigen" and step.get("ok")
           for step in steps):
        parts.append(_batch_confirmation(steps))
    return "\n\n".join(parts)


def _response_needs_continuation(text: str, done_reason: str = "") -> bool:
    """Erkennt Längenstopps und Antworten, die nur die nächste Aktion ankündigen."""
    if (done_reason or "").casefold() in {"length", "max_tokens", "limit"}:
        return True
    value = (text or "").strip()
    if not value:
        return True
    if value.count("```") % 2 or value.count("~~~") % 2:
        return True

    tail = value[-700:]
    last_paragraph = re.split(r"\n\s*\n", tail)[-1].strip()
    promise = re.compile(
        r"(?:^|[.!?]\s+)(?:ich\s+werde\b|ich\s+(?:beginne|starte|lese|prüfe|"
        r"analysiere|untersuche|verschiebe|bearbeite|korrigiere|erstelle)\b.{0,35}"
        r"\b(?:nun|jetzt|zuerst|als\s+nächstes)\b|beginnen\s+wir\b|"
        r"als\s+nächstes\b|im\s+nächsten\s+schritt\b)",
        re.IGNORECASE | re.DOTALL,
    )
    if promise.search(last_paragraph):
        return True
    if last_paragraph.endswith((":", "-", "–", "…")):
        return True
    if re.search(
        r"\b(?:ausschließlich|beziehungsweise|insbesondere|sowie|und|oder|mit|"
        r"auf|für|dass|weil|damit|indem|um)\s*$",
        last_paragraph,
        re.IGNORECASE,
    ):
        return True
    return False


def _continuation_instruction(done_reason: str = "") -> str:
    reason = (
        "Die vorige Ausgabe wurde wegen der Längenbegrenzung beendet. "
        if (done_reason or "").casefold() in {"length", "max_tokens", "limit"}
        else "Die vorige Ausgabe endet mit einer bloßen Arbeitsankündigung. "
    )
    return (
        reason
        + "Setze unmittelbar an der offenen Stelle fort, ohne den bisherigen Text "
          "zu wiederholen. Führe angekündigte Aktionen jetzt mit den verfügbaren "
          "Werkzeugen aus. Beende erst mit einem vollständigen, überprüften Ergebnis; "
          "kündige keinen weiteren Schritt nur an."
    )


def _incomplete_confirmation(missing: List[str]) -> str:
    if "organize_files" in missing:
        return (
            "Die verlangte Dateiordnung konnte trotz der automatischen Fortsetzung "
            "nicht vollständig ausgeführt werden. Es wurden keine unbestätigten "
            "Ersatzänderungen vorgenommen."
        )
    if "batch_edit" in missing:
        return "Die globale Vault-Bearbeitung konnte nicht vollständig abgeschlossen werden."
    if "edit" in missing:
        return (
            "Die bestehende Notiz wurde nicht pauschal überschrieben, weil die "
            "verlangte Änderung nicht sicher genug abgegrenzt werden konnte."
        )
    return "Der angeforderte Vault-Auftrag konnte nicht vollständig ausgeführt werden."


def _append_to_latest_user(history: List[Dict[str, Any]], context: str) -> None:
    if not context:
        return
    for message in reversed(history):
        if message.get("role") == "user":
            message["content"] = f"{message.get('content', '')}\n\n{context}"
            return


def _system_prompt(user_prompt: str, root: Optional[Path], overview: str = "",
                   vault_guide: str = "", action_contract: str = "") -> str:
    """Setzt die System-Anweisung zusammen.

    Der Arbeitschat bleibt auch ohne erreichbaren Vault auf seinen Ablagezweck
    begrenzt. Mit Vault bekommt das Modell zusätzlich Ordnerstruktur und Regeln.
    """
    teile = [user_prompt.strip()] if user_prompt.strip() else []
    teile.append(
        "DIES IST DER ARBEITSCHAT 'WISSEN ERWEITERN'. Sein einziger Zweck ist, "
        "Informationen und Dateien in den Vault aufzunehmen, vorhandene Notizen "
        "zu ergänzen oder den Vault zu organisieren. Beantworte hier keine reinen "
        "Wissensfragen. Wenn keine Ablage-, Import-, Ergänzungs- oder "
        "Bearbeitungsabsicht erkennbar ist, verweise knapp auf den getrennten "
        "Bereich 'Wissen fragen'."
    )
    if root is not None:
        teile.append(BASE_INSTRUCTIONS)
        if vault_guide:
            teile.append(
                "VERBINDLICHE VAULT-HAUPTDATEI '00 Inhalt.md':\n"
                "Befolge ihre Gestaltungs-, Ablage- und Linkregeln. Eine aktuelle, "
                "ausdrückliche Nutzeranweisung darf die betreffende Regel ändern; "
                "alle nicht angesprochenen Regeln bleiben maßgeblich.\n\n"
                + vault_guide
            )
        if overview:
            teile.append(f"Vault '{root.name}':\n{overview}")
        if action_contract:
            teile.append(action_contract)
    return "\n\n".join(teile)


def _question_system_prompt(user_prompt: str) -> str:
    """Systemrahmen für den reinen Lese- und Fragen-Chat.

    Der Modus bekommt absichtlich weder Vault-Übersicht noch Werkzeuge. Lokale
    Treffer werden später als zitierbarer Kontext an die Nutzerfrage gehängt.
    """
    teile = [user_prompt.strip()] if user_prompt.strip() else []
    teile.append(
        "DIES IST DER LESECHAT 'WISSEN FRAGEN'. Beantworte Fragen direkt und "
        "hilfreich. Nutze die beigefügten Auszüge aus der lokalen Wissensbasis "
        "vorrangig, wenn sie relevant sind, und zitiere sie mit den angegebenen "
        "WikiLinks. Nenne Seitenzahlen nur, wenn sie ausdrücklich an einer "
        "PDF-Quelle stehen; für Markdown und DOCX keine Seitenzahlen erfinden. "
        "Du darfst fehlendes Wissen mit "
        "deinem allgemeinen Modellwissen ergänzen, musst aber klar kenntlich "
        "machen, was nicht aus der lokalen Wissensbasis stammt. Wenn lokale "
        "Quellen und allgemeines Wissen einander widersprechen, benenne den "
        "Widerspruch statt ihn zu verdecken. Du hast in diesem Modus keinen "
        "Schreibzugriff: Behaupte niemals, Dateien, Notizen oder den Vault erstellt, "
        "geändert, verschoben oder gelöscht zu haben. Für solche Aufträge verweise "
        "auf den getrennten Bereich 'Wissen erweitern'."
    )
    return "\n\n".join(teile)


def _build_history(database, chat_id: str, system_prompt: str,
                   attachment_note: str = "") -> List[Dict[str, Any]]:
    """Baut die Nachrichtenliste für Ollama inklusive Bildanhängen."""
    messages: List[Dict[str, Any]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})

    for row in database.list_messages(chat_id):
        if row["role"] == "assistant" and not row["content"].strip():
            continue  # leere Platzhalter (z. B. abgebrochene Antworten) überspringen
        message: Dict[str, Any] = {"role": row["role"], "content": row["content"]}
        images, extra_text = [], []
        for attachment in row.get("attachments") or []:
            if attachment.get("kind") == "image" and attachment.get("data"):
                images.append(attachment["data"])
            elif attachment.get("text"):
                label = attachment.get("path") or attachment.get("name") or "Anhang"
                extra_text.append(f"\n\n--- Inhalt von {label} ---\n{attachment['text']}")
        if images:
            message["images"] = images
        if extra_text:
            message["content"] = message["content"] + "".join(extra_text)
        messages.append(message)

    # Der Hinweis auf Anhänge gehört an die letzte Nutzernachricht: dort wirkt er
    # zuverlässig. Im gespeicherten Chatverlauf taucht er nicht auf.
    if attachment_note:
        for message in reversed(messages):
            if message["role"] == "user":
                message["content"] = f"{message['content']}\n\n{attachment_note}"
                break

    return messages
