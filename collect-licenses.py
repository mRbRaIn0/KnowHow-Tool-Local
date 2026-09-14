"""Collect installed dependency notices for the Windows release (offline)."""
from importlib import metadata
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sections = [
    "KnowHow Tool V1.2 — third-party notices\n\n"
    "Third-party components retain their original licenses. The application's\n"
    "proprietary license does not apply to them. This inventory includes the\n"
    "installed build environment as well as runtime dependencies. Models and\n"
    "Ollama are installed separately and are not part of this release.\n"
]
python_license = Path(sys.base_prefix) / "LICENSE.txt"
sections.append("Python " + sys.version.split()[0] + "\n\n" + python_license.read_text(encoding="utf-8"))
for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
    name = dist.metadata["Name"]
    header = f"{name} {dist.version}\n"
    for key in ("License-Expression", "License", "Author", "Home-page"):
        if value := dist.metadata.get(key):
            header += f"{key}: {value}\n"
    texts = []
    for file in sorted(dist.files or [], key=str):
        if any(word in file.name.lower() for word in ("license", "licence", "notice", "copying")):
            path = Path(dist.locate_file(file))
            if path.is_file() and path.suffix.lower() not in {".py", ".pyc", ".exe", ".dll"}:
                texts.append(f"\n--- {file} ---\n" + path.read_text(encoding="utf-8", errors="replace"))
    sections.append(header + "\n".join(texts))
(root / "THIRD_PARTY_NOTICES.txt").write_text("\n\n" + ("\n\n" + "=" * 78 + "\n\n").join(sections), encoding="utf-8")
print("THIRD_PARTY_NOTICES.txt generated")
