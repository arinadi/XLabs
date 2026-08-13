"""installer/iobench.py: fio-based isolation-preset scoring.

    python tests/test_iobench.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

FIO_JSON = json.dumps(
    {
        "fio version": "fio-3.33",
        "jobs": [
            {"jobname": "randrw4k", "read": {"iops": 100.0}, "write": {"iops": 50.0}},
            {"jobname": "filecreate", "read": {"iops": 0.0}, "write": {"iops": 400.0}},
            {"jobname": "filestat", "read": {"iops": 900.0}, "write": {"iops": 0.0}},
            {"jobname": "filedelete", "read": {"iops": 0.0}, "write": {"iops": 350.0}},
        ],
    }
)


def test_iobench_parse_score_sums_every_job() -> None:
    from installer import iobench

    score = iobench._parse_score(FIO_JSON)
    check(score == 1800.0, f"expected the sum of every job's iops, got {score}")


def test_iobench_parse_score_skips_leading_noise() -> None:
    """fio sometimes prints a warning line before the JSON blob; the parser
    must find the JSON rather than failing the whole run over it."""
    from installer import iobench

    noisy = "fio: some warning about a tunable\n" + FIO_JSON
    check(iobench._parse_score(noisy) == 1800.0, "leading noise broke the parse")


def test_iobench_parse_score_handles_garbage() -> None:
    from installer import iobench

    check(iobench._parse_score("") is None, "empty output must not crash the parse")
    check(iobench._parse_score("not json at all") is None, "non-JSON output must not crash")
    check(iobench._parse_score('{"jobs": []}') is None, "an empty jobs list must score as None")


def test_iobench_work_dir_is_not_shared_tmp() -> None:
    """The bench must target the container's own rootfs, not /tmp — /tmp is
    --shared-tmp, a bind straight through to Termux's filesystem, so it
    would score identically under every isolation preset and the whole
    benchmark would measure nothing."""
    from installer import iobench

    check(not iobench.WORK_DIR.startswith("/tmp"), f"WORK_DIR is under /tmp: {iobench.WORK_DIR}")
    check(iobench.WORK_DIR in iobench.BENCH_SCRIPT, "the script does not reference WORK_DIR")


TESTS = [
    test_iobench_parse_score_sums_every_job,
    test_iobench_parse_score_skips_leading_noise,
    test_iobench_parse_score_handles_garbage,
    test_iobench_work_dir_is_not_shared_tmp,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
