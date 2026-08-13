"""Measure which proot isolation preset is fastest on this device, then keep
it.

--isolated trades away /sdcard and Termux $HOME access for fewer bind-mount
entries proot's ptrace layer has to resolve on every syscall. Whether that
trade pays off depends on how many binds the device would otherwise carry
and how syscall-heavy the actual workload is — unknown ahead of time, so
this measures it with fio rather than assuming, the same way bench.py
measures GPU presets instead of guessing from published hardware guidance.

The workload targets the container's own rootfs (/root), not /tmp: /tmp is
--shared-tmp, a bind straight through to Termux's own filesystem, so it
would score identically under every preset and prove nothing about the
binds actually being varied. fio's filecreate/filestat/filedelete engines
mimic the metadata-heavy pattern (`npm install`, codebase-wide search) that
issue research identified as what proot's ptrace overhead actually hits
hardest — a small-file randrw job covers ordinary read/write on top of that.
"""

from __future__ import annotations

import json
from typing import Callable

from . import config, isolation
from .const import CONTAINER_NAME
from .system import container_command, is_installed, run_cmd, stream_cmd, write_container_script

Log = Callable[[str], None]

IOBENCH_SCRIPT_NAME = "xlabs-iobench.sh"
WORK_DIR = "/root/.cache/xlabs-iobench"

# Short enough that testing three presets back to back stays under a minute;
# long enough that a cold cache doesn't dominate the number.
RUNTIME_SECONDS = 2
NRFILES = 150

JOB_FILE = f"""[global]
directory={WORK_DIR}
group_reporting=1

[randrw4k]
stonewall
rw=randrw
bs=4k
size=4m
ioengine=sync
runtime={RUNTIME_SECONDS}
time_based=1

[filecreate]
stonewall
ioengine=filecreate
nrfiles={NRFILES}
filesize=4k

[filestat]
stonewall
ioengine=filestat
nrfiles={NRFILES}

[filedelete]
stonewall
ioengine=filedelete
nrfiles={NRFILES}
"""

BENCH_SCRIPT = f"""#!/bin/bash
mkdir -p {WORK_DIR}
cat > /tmp/xlabs-iobench.fio <<'FIOEOF'
{JOB_FILE}FIOEOF
fio --output-format=json /tmp/xlabs-iobench.fio
rc=$?
rm -rf {WORK_DIR}
exit $rc
"""


def _parse_score(output: str) -> float | None:
    """Total IOPS across every job's read and write phase.

    fio sometimes prints a warning line or two before the JSON blob (a
    missing tunable, a libaio fallback notice); slicing from the first "{"
    skips those rather than failing the whole parse over cosmetic noise.
    """
    start = output.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(output[start:])
    except (ValueError, json.JSONDecodeError):
        return None

    jobs = data.get("jobs", [])
    if not jobs:
        return None

    total = 0.0
    for job in jobs:
        for direction in ("read", "write"):
            total += job.get(direction, {}).get("iops", 0.0)
    return total if total > 0 else None


def fio_installed() -> bool:
    rc, _ = run_cmd(
        f"proot-distro login {CONTAINER_NAME} -- bash -c 'command -v fio'",
        timeout=90,
    )
    return rc == 0


def install_fio(log: Log) -> bool:
    script = (
        "#!/bin/bash\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        "apt-get update\n"
        "apt-get install -y fio\n"
    )
    if not write_container_script("xlabs-fio-install.sh", script):
        log("[red]Could not write the install script.[/red]")
        return False
    rc = stream_cmd(
        container_command("xlabs-fio-install.sh"),
        log,
        timeout=1800,
    )
    return rc == 0


# A preset has to beat the current default by more than noise before it's
# worth the /sdcard and $HOME access it costs — otherwise "isolated" would
# win on measurement jitter alone and nobody would notice the trade until
# they went looking for a file that used to just be there.
WORTHWHILE_MARGIN = 1.05


def run(log: Log) -> None:
    """Benchmark each isolation preset and keep the winner, if it's worth it."""
    if not is_installed():
        log("[red]No container — install it from the menu first.[/red]")
        return

    if not fio_installed():
        log("fio is not in the container, installing it...")
        if not install_fio(log):
            log("[red]Could not install fio.[/red]")
            return
        log("")

    if not write_container_script(IOBENCH_SCRIPT_NAME, BENCH_SCRIPT):
        log("[red]Could not write the benchmark script.[/red]")
        return

    results: list[tuple[isolation.Preset, float | None]] = []

    for preset in isolation.PRESETS:
        log(f"── {preset.name}: {preset.description}")

        captured: list[str] = []

        def collect(line: str, sink: list[str] = captured) -> None:
            sink.append(line)

        rc = stream_cmd(
            container_command(IOBENCH_SCRIPT_NAME, isolation_preset=preset),
            collect,
            timeout=120,
        )
        score = _parse_score("\n".join(captured))
        results.append((preset, score))

        if score is None:
            log(f"    no score (exit {rc})")
            for line in captured[-3:]:
                log(f"    {line}")
        else:
            log(f"    {score:.0f} combined IOPS")
        log("")

    log("── Results ───────────────────────────────────")
    for preset, score in results:
        log(f"  {preset.name:<18} {'failed' if score is None else f'{score:.0f}'}")
    log("")

    scored = [(p, s) for p, s in results if s is not None]
    if not scored:
        log("[red]Nothing produced a score.[/red]")
        return

    scores = dict(scored)
    best, best_score = max(scored, key=lambda pair: pair[1])
    baseline = scores.get(isolation.DEFAULT_PRESET)

    log(f"[bold green]Best: {best.name} ({best_score:.0f} IOPS)[/bold green]")

    if best is isolation.DEFAULT_PRESET or baseline is None:
        keep, keep_score = isolation.DEFAULT_PRESET, baseline or best_score
    elif best_score >= baseline * WORTHWHILE_MARGIN:
        keep, keep_score = best, best_score
        log(f"  {best_score / baseline:.2f}x the default preset — worth the trade")
    else:
        keep, keep_score = isolation.DEFAULT_PRESET, baseline
        log("  within noise of the default — keeping full Android/host access")

    if isolation.save_preset(keep, keep_score):
        log(f"  saved to {config.CONFIG_PATH}")
        log("  Start Desktop and every other container session will use it from now on.")
    else:
        log("  [yellow]Could not save the result.[/yellow]")
