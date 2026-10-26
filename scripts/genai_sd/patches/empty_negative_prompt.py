#!/usr/bin/env python3
"""Keep an explicit empty --n_prompt from being replaced by model defaults."""

from __future__ import annotations

import sys
from pathlib import Path

OLD = 'if not getattr(args, "n_prompt", None):'
NEW = 'if getattr(args, "n_prompt", None) is None:'


def patch_runner(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    if NEW in source:
        return False
    if source.count(OLD) != 1:
        raise SystemExit(f"expected exactly one runner default expression in {path}")
    path.write_text(source.replace(OLD, NEW), encoding="utf-8")
    return True


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} PATH_TO_runner_args.py")
    changed = patch_runner(Path(sys.argv[1]))
    print("patched explicit negative-prompt handling" if changed else "already patched")


if __name__ == "__main__":
    main()
