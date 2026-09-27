from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).parent.parent / "docs"
SOURCE = DOCS / "en"
TRANSLATIONS = sorted(p for p in DOCS.iterdir() if p.is_dir() and p != SOURCE)
PAGES = sorted(p.name for p in SOURCE.glob("*.md"))

_FENCED_BLOCK = re.compile(r"^```.*?^```", re.S | re.M)


def _code_blocks(page: Path) -> list[str]:
    return _FENCED_BLOCK.findall(page.read_text("utf-8"))


@pytest.mark.parametrize("lang", TRANSLATIONS, ids=lambda p: p.name)
@pytest.mark.parametrize("page", PAGES)
def test_translation_matches_english(lang: Path, page: str) -> None:
    translated = lang / page
    assert translated.exists(), f"{translated} is missing; translate docs/en/{page}"
    assert _code_blocks(translated) == _code_blocks(SOURCE / page), (
        f"Code blocks in {translated} differ from docs/en/{page}. "
        "Code stays identical across languages; update the translation."
    )
