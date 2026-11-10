"""Apply migrations and (re)load the word database.

    python -m backend.database.init_db          # migrate + seed
    python -m backend.database.init_db --seed   # seed only
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from ..core.config import REPO_ROOT, get_settings
from ..models import Word
from .session import SessionLocal

log = logging.getLogger(__name__)
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url or get_settings().database_url)
    return cfg


def migrate(url: str | None = None) -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(url), "head")


def seed_words(words_file: Path | None = None) -> int:
    """Insert or update words from data/words.json (idempotent)."""
    path = words_file or get_settings().words_file
    entries = json.loads(path.read_text(encoding="utf-8"))["words"]
    fields = ["word", "ipa", "phonemes", "arpabet", "syllables", "difficulty", "category", "category_label",
              "target_sounds", "evaluation_features", "variants", "stress_pattern", "syllable_breakdown", "notes"]
    with SessionLocal() as db:
        existing = {w.id: w for w in db.execute(select(Word)).scalars()}
        for e in entries:
            w = existing.get(e["id"]) or Word(id=e["id"])
            for f in fields:
                setattr(w, f, e.get(f))
            db.add(w)
        db.commit()
    return len(entries)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="only seed words")
    args = ap.parse_args()
    if not args.seed:
        migrate()
        print("migrations applied")
    print(f"seeded {seed_words()} words")


if __name__ == "__main__":
    main()
