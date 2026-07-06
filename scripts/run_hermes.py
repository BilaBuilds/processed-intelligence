from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enrichment.agents.hermes import HermesAgent

DEFAULT_CONFIG = REPO_ROOT / "enrichment" / "config.yaml"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "hermes" / "runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Hermes lead enrichment.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_id = datetime.now(UTC).strftime("hermes_%Y%m%d_%H%M%S")
    run_dir = args.output_root / run_id
    output_path = run_dir / "enriched_output.csv"
    summary_path = run_dir / "summary.json"

    agent = HermesAgent.from_config(args.config)
    try:
        summary = agent.enrich_csv(args.input, output_path, summary_path, run_id=run_id)
    finally:
        agent.close()

    print(summary.summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
