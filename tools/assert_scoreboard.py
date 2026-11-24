#!/usr/bin/env python3
"""Parses kit/evaluate.py output and verifies policy and truth violations are within limits.

Usage:
    python tools/assert_scoreboard.py <file> --max-policy 0 --max-truth 0
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_scoreboard(text: str) -> tuple[int, int]:
    """Extract policy and truth violation counts from evaluate.py output."""
    policy_match = re.search(r"policy violations\s+(\d+)", text)
    truth_match = re.search(r"truth violations\s+(\d+)", text)

    if not policy_match or not truth_match:
        raise ValueError(
            "Could not find 'policy violations' or 'truth violations' in evaluate.py output format."
        )

    return int(policy_match.group(1)), int(truth_match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert scoreboard policy and truth violations limits.")
    parser.add_argument("file", help="Path to evaluate.py output file")
    parser.add_argument("--max-policy", type=int, default=0, help="Maximum allowed policy violations (default: 0)")
    parser.add_argument("--max-truth", type=int, default=0, help="Maximum allowed truth violations (default: 0)")

    args = parser.parse_args()
    file_path = Path(args.file)

    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        return 2

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        return 2

    try:
        policy_violations, truth_violations = parse_scoreboard(content)
    except ValueError as e:
        print(f"Format Error in {file_path}: {e}", file=sys.stderr)
        return 2

    failed = False
    if policy_violations > args.max_policy:
        print(
            f"FAILED: Policy violations {policy_violations} exceed maximum allowed {args.max_policy}",
            file=sys.stderr,
        )
        failed = True

    if truth_violations > args.max_truth:
        print(
            f"FAILED: Truth violations {truth_violations} exceed maximum allowed {args.max_truth}",
            file=sys.stderr,
        )
        failed = True

    if failed:
        return 1

    print(
        f"OK: Scoreboard passed (policy: {policy_violations} <= {args.max_policy}, "
        f"truth: {truth_violations} <= {args.max_truth})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
