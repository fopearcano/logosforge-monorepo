"""Test-only CLI: produce a local Writer QA report via the fake provider.

Drives the real Assistant contract layer (`route` → `validate`) over the
scenario matrix, generating each response with the deterministic **fake
provider** in `logosforge.qa_mode` (NO real provider / network / cloud /
credentials), logging redacted structured events, then exporting
`reports/writer_qa/local_latest.{json,md}` (git-ignored).

This is local QA tooling, not production code — it is never imported by the app.

Usage:
    python tools/writer_qa/export_local_report.py
    python tools/writer_qa/export_local_report.py --suite manuscript
    python tools/writer_qa/export_local_report.py --profile invalid_planning_markdown
    python tools/writer_qa/export_local_report.py --report reports/writer_qa/local_latest
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from logosforge import qa_mode                                       # noqa: E402
from logosforge.assistant_contract import (                         # noqa: E402
    route, system_prompt_for, validate,
)
from tools.writer_qa.scenarios import get_suite                        # noqa: E402


def run(suite: str = "all", profile_override: str = "",
        report_base: str | None = None, log_dir: str = "") -> tuple[str, str]:
    """Generate fake responses across a suite, log redacted events, export."""
    if log_dir:
        import os
        os.environ[qa_mode.LOG_DIR_ENV] = log_dir
    qa_mode.reset_log()

    for sc in get_suite(suite):
        has_target = sc.target not in ("no_target", "", None)
        contract = route(
            entry_point=sc.entry_point, section=sc.section,
            writing_mode=sc.writing_mode, action=sc.action,
            user_instruction=sc.instruction, has_target=has_target,
        )
        messages = [
            {"role": "system", "content": system_prompt_for(contract)},
            {"role": "user", "content": sc.instruction},
        ]
        prof = profile_override or sc.provider_profile
        try:
            text = qa_mode.fake_completion(messages, profile=prof)
        except qa_mode.FakeProviderError as exc:
            qa_mode.log_event(
                "provider_error", scenario=sc.name, section=sc.section,
                writing_mode=sc.writing_mode, action=sc.action,
                profile=prof, detail=str(exc),
            )
            continue

        res = validate(text, contract)
        valid = res.status == "valid"
        qa_mode.log_event(
            "assistant_response",
            scenario=sc.name,
            entry_point=contract.entry_point,
            section=contract.section,
            writing_mode=contract.writing_mode,
            action=contract.action,
            target=contract.target,
            output_kind=contract.output_kind,
            validator_profile=contract.validator_profile,
            validation_status=res.status,
            validation_reasons=list(res.reasons),
            response_valid=valid,
            apply_allowed=bool(valid and res.apply_allowed),
            copy_allowed=bool(res.copy_allowed),
            withheld=bool(res.diagnostic_only),
            profile=prof,
            response_excerpt=text,
        )

    return qa_mode.export_report(report_base)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export a local Writer QA report.")
    ap.add_argument("--suite", default="all",
                    help="all | assistant | manuscript | outline | notes | "
                         "psyke | timeline | chat | dexter")
    ap.add_argument("--profile", default="",
                    help="Force one fake-provider profile for every scenario.")
    ap.add_argument("--report", default=None,
                    help="Report base path (default reports/writer_qa/local_latest).")
    ap.add_argument("--log-dir", default="",
                    help="Override the QA session-log directory.")
    args = ap.parse_args(argv)

    json_path, md_path = run(
        suite=args.suite, profile_override=args.profile,
        report_base=args.report, log_dir=args.log_dir,
    )
    summary = qa_mode._summarize(qa_mode.buffered_events())
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Events: {summary['events_total']} "
          f"(responses {summary['responses']}, "
          f"withheld {summary['withheld_responses']}, "
          f"apply-eligible {summary['applyable_responses']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
