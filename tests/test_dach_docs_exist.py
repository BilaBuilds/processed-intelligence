from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


REQUIRED_DOCS = [
    DOCS / "DACH_EXPANSION_PLAN.md",
    DOCS / "DACH_SOURCE_RESEARCH_CHECKLIST.md",
    DOCS / "DACH_DATA_MODEL.md",
]


def read_all_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in REQUIRED_DOCS)


def test_dach_docs_exist():
    for path in REQUIRED_DOCS:
        assert path.exists(), f"Missing required DACH doc: {path}"


def test_dach_countries_are_mentioned():
    docs_text = read_all_docs()

    for country in ["Germany", "Austria", "Switzerland"]:
        assert country in docs_text


def test_tenderned_untouched_statement_appears():
    plan_text = (DOCS / "DACH_EXPANSION_PLAN.md").read_text(encoding="utf-8")

    assert "TenderNed demo remains untouched" in plan_text


def test_run_pipeline_is_not_modified():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "run_pipeline.py"],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "run_pipeline.py has local modifications"
