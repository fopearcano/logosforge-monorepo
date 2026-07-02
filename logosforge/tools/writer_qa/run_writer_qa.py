#!/usr/bin/env python3
"""Writer QA harness CLI — run writer scenarios against the real Assistant
contract layer with a deterministic fake provider, and emit bug reports.

    python tools/writer_qa/run_writer_qa.py --suite alpha --report reports/writer_qa/latest
    python tools/writer_qa/run_writer_qa.py --suite assistant
    python tools/writer_qa/run_writer_qa.py --suite manuscript

Exit code is non-zero when BLOCKER findings exceed --max-blocker (default 0), so
it can gate CI. Uses NO real provider, NO network, NO cloud/GitHub, and writes
only under the chosen --report path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.writer_qa.reporting import summarize, write_reports   # noqa: E402
from tools.writer_qa.scenarios import get_suite                  # noqa: E402
from tools.writer_qa.validators import run_suite                 # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LogosForge Writer QA harness")
    ap.add_argument("--suite", default="alpha",
                    help="alpha | all | assistant | manuscript | outline | "
                         "notes | psyke | timeline | chat | dexter")
    ap.add_argument("--report", default="reports/writer_qa/latest",
                    help="output path prefix (writes <prefix>.json/.md)")
    ap.add_argument("--max-blocker", type=int, default=0,
                    help="allowed BLOCKER findings before failing (default 0)")
    ap.add_argument("--max-high", type=int, default=-1,
                    help="allowed HIGH findings before failing (-1 = unlimited)")
    args = ap.parse_args(argv)

    scenarios = get_suite(args.suite)
    bugs, total = run_suite(scenarios)
    summary = summarize(bugs, total)
    json_path, md_path = write_reports(bugs, summary, args.report)

    sev = summary["by_severity"]
    print(f"Writer QA: {total} scenarios · {summary['bugs']} bugs "
          f"(BLOCKER {sev['BLOCKER']} · HIGH {sev['HIGH']} · "
          f"MEDIUM {sev['MEDIUM']} · LOW {sev['LOW']})")
    print(f"Reports: {json_path} · {md_path}")

    failed = sev["BLOCKER"] > args.max_blocker
    if args.max_high >= 0 and sev["HIGH"] > args.max_high:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
