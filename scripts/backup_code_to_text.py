import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = REPO_ROOT / "agent_ops" / "backups"

INCLUDE_EXTS = {".py", ".json", ".md", ".html"}

EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
}

# Exclude high-volume or sensitive areas.
EXCLUDE_REL_DIRS = {
    Path("data") / "runs",
    Path("agent_ops") / "backups",
}

EXCLUDE_FILE_NAMES = {
    ".env",
}


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _should_exclude(path: Path) -> bool:
    # directory name filters
    for part in path.parts:
        if part in EXCLUDE_DIR_NAMES:
            return True

    # explicit relative directory exclusions
    rel = path.relative_to(REPO_ROOT)
    for ex in EXCLUDE_REL_DIRS:
        if _is_under(rel, ex):
            return True

    # .env and variants
    if rel.name in EXCLUDE_FILE_NAMES or rel.name.startswith(".env."):
        return True

    return False


def _iter_files() -> Iterable[Path]:
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in INCLUDE_EXTS:
            continue
        if _should_exclude(path):
            continue
        yield path


def main() -> int:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = BACKUPS_DIR / f"code_snapshot_{ts}.txt"

    files: List[Path] = sorted(_iter_files(), key=lambda p: p.as_posix())

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"# Code Snapshot ({ts} UTC)\n")
        out.write(f"# Root: {REPO_ROOT.as_posix()}\n\n")
        for path in files:
            rel = path.relative_to(REPO_ROOT).as_posix()
            out.write(f"===== {rel} =====\n")
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                out.write(f"<<ERROR reading file: {e}>>\n\n")
                continue
            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")
            out.write("\n")

    print(out_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

