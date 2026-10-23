import json
import os
from pathlib import Path

import pytest
from accra_language import Config

from accra_csharp import CSharp

PAPERS = Path(os.environ.get("CSHARP_PAPERS", "/tmp/papers-csharp"))
CASES = json.loads(
    (Path(__file__).with_name("papers.json")).read_text(encoding="utf-8")
)


def test_article_dataset_covers_at_least_fifty_papers():
    assert len(CASES) >= 50


def _papers_present() -> bool:
    return all((PAPERS / case["name"]).is_dir() for case in CASES)


@pytest.mark.skipif(
    not _papers_present(),
    reason="C# article checkouts are not in CSHARP_PAPERS",
)
@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_article_source_builds_on_the_selected_sdk(case: dict):
    root = PAPERS / case["name"]
    source = (root / case["source"]).read_text(encoding="utf-8-sig", errors="replace")
    assert case["syntax"] in source
    for project in case["projects"]:
        result = CSharp(Config(cwd=root / project)).build()
        messages = [error.message for error in result.errors]
        assert result.success is True, messages
        if case.get("library"):
            built = list(root.rglob(case["library"]))
            assert built, case["library"]
    print(f"{case['article']}: built")
