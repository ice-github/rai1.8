#!/usr/bin/env python3
"""Run a command while sampling process-tree and system memory (Linux)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--min-available-gib", type=float, default=2.0)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        ap.error("a command is required after --")
    args.csv.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(command, start_new_session=True)
    root = psutil.Process(proc.pid)
    start = time.monotonic()
    samples = 0
    peak_rss = peak_pss = 0
    min_available = float("inf")
    reason = "completed"

    with args.csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["elapsed_s", "system_mem_available_gib", "tree_rss_gib", "tree_pss_gib", "tree_swap_gib", "process_count"])
        while proc.poll() is None:
            now = time.monotonic()
            elapsed = now - start
            vm = psutil.virtual_memory()
            available = vm.available / 1024**3
            min_available = min(min_available, available)
            procs = []
            try:
                procs = [root, *root.children(recursive=True)]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            rss = pss = swap = 0
            count = 0
            for p in procs:
                try:
                    m = p.memory_full_info()
                    rss += m.rss
                    pss += getattr(m, "pss", m.rss)
                    swap += getattr(m, "swap", 0)
                    count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            rss_gib, pss_gib = rss / 1024**3, pss / 1024**3
            peak_rss, peak_pss = max(peak_rss, rss_gib), max(peak_pss, pss_gib)
            writer.writerow([f"{elapsed:.3f}", f"{available:.3f}", f"{rss_gib:.3f}", f"{pss_gib:.3f}", f"{swap/1024**3:.3f}", count])
            samples += 1
            f.flush()
            if available < args.min_available_gib:
                reason = "memavailable_below_threshold"
                break
            if elapsed >= args.timeout:
                reason = "timeout"
                break
            time.sleep(args.interval)

    if reason != "completed" and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    rc = proc.wait()
    elapsed = time.monotonic() - start
    summary = {
        "command": command,
        "stop_reason": reason,
        "exit_code": rc,
        "duration_seconds": round(elapsed, 3),
        "samples": samples,
        "peak_process_tree_rss_gib": round(peak_rss, 3),
        "peak_process_tree_pss_gib": round(peak_pss, 3),
        "minimum_system_mem_available_gib": round(min_available, 3) if min_available != float("inf") else None,
        "interval_seconds": args.interval,
        "minimum_available_gib": args.min_available_gib,
        "timeout_seconds": args.timeout,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Memory monitor: {reason}; peak RSS/PSS={peak_rss:.2f}/{peak_pss:.2f} GiB; min MemAvailable={min_available:.2f} GiB", flush=True)
    if reason == "memavailable_below_threshold":
        return 75
    if reason == "timeout":
        return 124
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
