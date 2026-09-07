"""Konfiguration und Profile.

Alles liegt lokal in data/config.json. Jedes Profil hat einen eigenen Vault
und eine eigene Datenbank — private und geschäftliche Daten bleiben dadurch
strikt getrennt.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

SOURCE_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))


def _application_root() -> Path:
    """Findet den beschreibbaren App-Ordner.

    Ein Build, der direkt im Projektordner unter ``dist`` liegt, soll dieselben
    Profile und Chats wie der Entwicklungsstarter verwenden. Eine an einen
    anderen Ort kopierte EXE bleibt dagegen portabel und legt ``data`` weiter
    neben sich an.
    """
    if not getattr(sys, "frozen", False):
        return SOURCE_ROOT
    executable_root = Path(sys.executable).resolve().parent
    project_root = executable_root.parent
    project_config = project_root / "data" / "config.json"
    if executable_root.name.casefold() == "dist" and project_config.is_file():
        return project_root
    return executable_root


APP_ROOT = _application_root()
DATA_DIR = APP_ROOT / "data"
PROFILE_DATA_DIR = DATA_DIR / "profiles"
CONFIG_PATH = DATA_DIR / "config.json"
BUNDLED_TEMPLATES = BUNDLE_ROOT / "templates"
LOG_DIR = DATA_DIR / "logs"

_BUILD_SUFFIXES = {".py", ".js", ".css", ".html"}


def build_fingerprint() -> str:
    """Kennung des vorliegenden Codestands.

    Eine bereits laufende Instanz verrät darüber, ob sie noch von vor einem
    Update stammt — sonst landet ein Neustart still beim alten Server.
    """
    if getattr(sys, "frozen", False):
        try:
            return f"exe-{int(Path(sys.executable).stat().st_mtime)}"
        except OSError:
            return "exe"
    neueste = 0.0
    for ordner in (SOURCE_ROOT / "backend", SOURCE_ROOT / "frontend"):
        for datei in ordner.rglob("*"):
            if datei.suffix.lower() in _BUILD_SUFFIXES:
                try:
                    neueste = max(neueste, datei.stat().st_mtime)
                except OSError:
                    continue
    return f"src-{int(neueste)}"


DEFAULT_SYSTEM_PROMPT = (
    "Du bist ein lokaler Obsidian-Wissensarchitekt und Datenversteher. "
    "Antworte präzise und standardmäßig auf Deutsch. Verdichte Informationen "
    "zu vollständigen, verknüpften und direkt nutzbaren Wissensnotizen."
)
LEGACY_SYSTEM_PROMPTS = {
    "Du bist eine lokale Wissensassistenz. Antworte präzise, sachlich und standardmäßig auf Deutsch.",
    "Du bist eine lokale Wissensassistenz. Antworte präzise, sachlich und standardmäßig auf Deutsch. Nutze Markdown für Struktur, Tabellen und Code.",
}


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3.5:9b"
    embed_model: str = "nomic-embed-text"


class AISettings(BaseModel):
    temperature: float = 0.7
    num_ctx: int = 8192
    rag_top_k: int = 6
    thinking: bool = False
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


class PrivacySettings(BaseModel):
    offline_mode: bool = True
    block_external_urls: bool = True
    telemetry: bool = False


class VaultSettings(BaseModel):
    path: str = ""
    attachments_dir: str = "90 Anhänge"
    templates_dir: str = "00 Templates"


class LibrarySettings(BaseModel):
    enabled: bool = False
    poll_seconds: int = Field(default=300, ge=30, le=86400)
    docling_python: str = ""
    docling_models: str = ""


class Profile(BaseModel):
    id: str
    name: str
    vault: VaultSettings = Field(default_factory=VaultSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    ai: AISettings = Field(default_factory=AISettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    library: LibrarySettings = Field(default_factory=LibrarySettings)

    @property
    def vault_path(self) -> Optional[Path]:
        if not self.vault.path:
            return None
        return Path(self.vault.path).expanduser()

    @property
    def data_dir(self) -> Path:
        return PROFILE_DATA_DIR / self.id

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


class UISettings(BaseModel):
    theme: str = "system"  # light | dark | system


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    # 0 = bei jedem Start einen freien Port vom System erfragen. Ein fester,
    # bekannter Port ist von jeder Webseite im selben Browser adressierbar;
    # ein wechselnder ist es praktisch nicht. Eine feste Zahl bleibt möglich.
    port: int = 0
    open_browser: bool = True


CONFIG_VERSION = 2


class AppConfig(BaseModel):
    version: int = CONFIG_VERSION
    active_profile: str = "privat"
    ui: UISettings = Field(default_factory=UISettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    profiles: List[Profile] = Field(default_factory=list)


def slugify(value: str) -> str:
    """Erzeugt eine dateisystem-sichere Profil-ID."""
    value = value.strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        value = value.replace(src, dst)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "profil"


def _default_config() -> AppConfig:
    return AppConfig(
        active_profile="privat",
        profiles=[Profile(id="privat", name="Privat")],
    )


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class ConfigStore:
    """Lädt und speichert die Konfiguration thread-sicher."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        with self._lock:
            if self._config is not None:
                return self._config
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    self._config = AppConfig.model_validate(raw)
                except Exception:
                    # Defekte Konfiguration niemals still verwerfen: beiseitelegen.
                    try:
                        self.path.replace(self.path.with_suffix(".broken.json"))
                    except OSError:
                        pass
                    self._config = _default_config()
            else:
                self._config = _default_config()
            self._ensure_consistency()
            self.save()
            return self._config

    def _ensure_consistency(self) -> None:
        cfg = self._config
        assert cfg is not None
        if cfg.version < 2:
            # Der frühere Standardport 5000 war überall gleich und damit ratbar.
            # Einmalig auf "automatisch" stellen; eine danach bewusst eingetragene
            # Portnummer bleibt unangetastet.
            if cfg.server.port == 5000:
                cfg.server.port = 0
            cfg.version = CONFIG_VERSION
        if not cfg.profiles:
            cfg.profiles = [Profile(id="privat", name="Privat")]
        if not any(p.id == cfg.active_profile for p in cfg.profiles):
            cfg.active_profile = cfg.profiles[0].id
        for profile in cfg.profiles:
            if profile.ai.system_prompt.strip() in LEGACY_SYSTEM_PROMPTS:
                profile.ai.system_prompt = DEFAULT_SYSTEM_PROMPT
            profile.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        with self._lock:
            if self._config is None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._config.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    @property
    def config(self) -> AppConfig:
        return self.load()

    def active_profile(self) -> Profile:
        cfg = self.load()
        for profile in cfg.profiles:
            if profile.id == cfg.active_profile:
                return profile
        return cfg.profiles[0]

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        for profile in self.load().profiles:
            if profile.id == profile_id:
                return profile
        return None

    def set_active_profile(self, profile_id: str) -> Profile:
        cfg = self.load()
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        cfg.active_profile = profile_id
        self.save()
        return profile

    def add_profile(self, name: str) -> Profile:
        cfg = self.load()
        base = slugify(name)
        pid, counter = base, 2
        existing = {p.id for p in cfg.profiles}
        while pid in existing:
            pid = f"{base}-{counter}"
            counter += 1
        profile = Profile(id=pid, name=name.strip() or pid)
        profile.data_dir.mkdir(parents=True, exist_ok=True)
        cfg.profiles.append(profile)
        self.save()
        return profile

    def delete_profile(self, profile_id: str) -> None:
        cfg = self.load()
        if len(cfg.profiles) <= 1:
            raise ValueError("Das letzte Profil kann nicht gelöscht werden.")
        cfg.profiles = [p for p in cfg.profiles if p.id != profile_id]
        if cfg.active_profile == profile_id:
            cfg.active_profile = cfg.profiles[0].id
        self.save()

    def update_profile(self, profile_id: str, patch: dict) -> Profile:
        """Teilweises Update eines Profils; verschachtelte dicts werden gemerged."""
        cfg = self.load()
        for index, profile in enumerate(cfg.profiles):
            if profile.id != profile_id:
                continue
            merged = _deep_merge(profile.model_dump(), patch)
            merged["id"] = profile_id  # ID bleibt unveränderlich
            updated = Profile.model_validate(merged)
            cfg.profiles[index] = updated
            updated.data_dir.mkdir(parents=True, exist_ok=True)
            self.save()
            return updated
        raise KeyError(profile_id)

    def update_ui(self, patch: dict) -> UISettings:
        cfg = self.load()
        cfg.ui = UISettings.model_validate(_deep_merge(cfg.ui.model_dump(), patch))
        self.save()
        return cfg.ui


store = ConfigStore()
