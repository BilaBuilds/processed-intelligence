"""
tests/test_architecture.py
==========================
Enforces architectural boundary: no src/supplier/ imports may appear in
core pipeline modules. The supplier layer consumes core outputs — the core
never imports from the supplier layer.

This test runs on every CI/test invocation and will catch accidental
boundary violations before they reach production.
"""
import re
from pathlib import Path

CORE_MODULES = [
    "src/ingest.py",
    "src/normalize.py",
    "src/match.py",
    "src/context.py",
    "src/buyer_intel.py",
    "src/patterns.py",
    "src/select.py",
    "src/decision.py",
    "src/dedupe.py",
    "src/notify",
    "run_pipeline.py",
]

SUPPLIER_IMPORT_PATTERN = re.compile(r"from\s+src\.supplier|import\s+src\.supplier")

REPO_ROOT = Path(__file__).parent.parent


def test_no_supplier_imports_in_core_modules():
    """Core pipeline modules must never import from src.supplier."""
    violations = []
    for module_path in CORE_MODULES:
        path = REPO_ROOT / module_path
        if path.is_dir():
            files = list(path.rglob("*.py"))
        else:
            files = [path] if path.exists() else []
        for f in files:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if SUPPLIER_IMPORT_PATTERN.search(content):
                violations.append(str(f.relative_to(REPO_ROOT)))

    assert violations == [], (
        f"Architectural boundary violation — supplier layer imported in core modules:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_schemas_importable():
    """All schema models must be importable without error."""
    from src.schemas.shortlist import ShortlistedTender
    from src.schemas.supplier import SupplierRecord
    from src.schemas.match import SupplierMatch
    assert ShortlistedTender
    assert SupplierRecord
    assert SupplierMatch


def test_utils_importable():
    from src.utils.region import decode_region, region_slug
    from src.utils.value_bands import classify_value_band
    assert decode_region
    assert region_slug
    assert classify_value_band
