#!/usr/bin/env python3
"""Normalize Linux shape-key ordering in AMD DDBUNDLE indices.

Only equal-length key names in the BXI0 key index are rewritten. The 48-byte
values, count, footer, file size and data payload remain unchanged. Original
bundles are preserved as ``.linux-shape.bak``.
The known format has a 4-byte record-key length, key bytes, a 48-byte value,
then a 4-byte index length, four zero reserved bytes, and the ``BXI0`` footer.
Unknown or malformed formats are rejected rather than guessed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
from pathlib import Path

MAGIC = b"BXI0"
VALUE_SIZE = 48
FIXED_AFTER_KEY = VALUE_SIZE
SWAP_PATTERNS = (
    (re.compile(rb"latent_h_(\d+)_latent_w_(\d+)_"),
     lambda m: b"latent_w_" + m.group(2) + b"_latent_h_" + m.group(1) + b"_"),
    (re.compile(rb"height_(\d+)_width_(\d+)_"),
     lambda m: b"width_" + m.group(2) + b"_height_" + m.group(1) + b"_"),
    (re.compile(
        rb"batch_(\d+)_(\d+)_w_(\d+)_h_(\d+)_state_dim1_(\d+)_max_length_(\d+)_"
    ), lambda m: (b"h_" + m.group(4) + b"_w_" + m.group(3)
                  + b"_batch_" + m.group(1) + b"_" + m.group(2)
                  + b"_state_dim1_" + m.group(5) + b"_max_length_" + m.group(6) + b"_")),
    (re.compile(rb"batch_(\d+)_(\d+)_w_(\d+)_h_(\d+)_state_dim1_(\d+)_"),
     lambda m: (b"h_" + m.group(4) + b"_w_" + m.group(3)
                + b"_batch_" + m.group(1) + b"_" + m.group(2)
                + b"_state_dim1_" + m.group(5) + b"_")),
)


def preferred_key(key: bytes) -> bytes | None:
    """Return the Linux runtime's ordering for known Ryzen AI shape keys."""
    alias = get_alias(key)
    if alias is not None:
        return alias
    # The Linux model's hidden-state key puts the image sequence before batch.
    m = re.fullmatch(
        rb"batch_size_(\d+)_img_seq_len_(\d+)_txt_seq_len_(\d+)_"
        rb"img_seq_len _ txt_seq_len_(\d+)_",
        key,
    )
    if m:
        return (b"img_seq_len_" + m.group(2) + b"_batch_size_" + m.group(1)
                + b"_txt_seq_len_" + m.group(3) + b"_img_seq_len _ txt_seq_len_"
                + m.group(4) + b"_")
    return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_alias(key: bytes) -> bytes | None:
    for pattern, swap in SWAP_PATTERNS:
        if pattern.search(key):
            return pattern.sub(swap, key)
    return None


def parse_records(index: bytes) -> list[tuple[bytes, bytes]]:
    if len(index) < 4:
        raise ValueError("truncated index count")
    count = struct.unpack_from("<I", index, 0)[0]
    records = []
    pos = 4
    for _ in range(count):
        start = pos
        if pos + 4 > len(index):
            raise ValueError("truncated key length")
        key_len = struct.unpack_from("<I", index, pos)[0]
        pos += 4
        if key_len == 0 or key_len > 4096 or pos + key_len + FIXED_AFTER_KEY > len(index):
            raise ValueError(f"invalid record/key length at index offset {start}")
        key = index[pos:pos + key_len]
        pos += key_len
        record_tail = index[pos:pos + FIXED_AFTER_KEY]
        pos += FIXED_AFTER_KEY
        records.append((key, index[start:pos]))
    # Ryzen AI 1.8 SD3 bundles carry a four-byte zero trailer after the counted
    # BXI0 records. Other observed bundles end immediately after the records.
    if index[pos:] not in (b"", b"\0\0\0\0"):
        raise ValueError("unexpected bytes after BXI0 index records")
    return records


def inspect(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 12 or data[-4:] != MAGIC:
        raise ValueError("missing BXI0 footer")
    # BXI0 v2 tail is: uint32 index-size, four reserved zero bytes, magic.
    index_len = struct.unpack_from("<I", data, len(data) - 12)[0]
    if data[-8:-4] != b"\0\0\0\0":
        raise ValueError("unknown BXI0 footer flags/reserved field")
    index_start = len(data) - 12 - index_len
    if index_start < 0:
        raise ValueError("index length extends before bundle")
    index = data[index_start:index_start + index_len]
    records = parse_records(index)
    keys = {key for key, _ in records}
    if len(keys) != len(records):
        raise ValueError("duplicate key in BXI0 index")
    aliases = []
    for key, record in records:
        alias = preferred_key(key)
        if alias is not None:
            # The value bytes and metadata are retained; only equal-length
            # dimension-order names are accepted.
            if len(alias) != len(key):
                raise ValueError(f"alias length differs for {key!r}")
            if alias in keys:
                raise ValueError(f"shape-key alias collision for {key!r}: {alias!r}")
            aliases.append((key, alias, record))
    return {
        "data": data,
        "index_start": index_start,
        "index": index,
        "records": records,
        "keys": keys,
        "aliases": aliases,
        "payload_sha256": sha256(data[:index_start]),
    }


def ensure_no_symlink_components(path: Path) -> None:
    """Prevent a supposedly isolated rewrite from following an overlay link."""
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink():
            raise ValueError(f"refusing to rewrite bundle through symlink path: {candidate}")


def apply(path: Path, check_only: bool) -> dict:
    parsed = inspect(path)
    if not parsed["aliases"]:
        backup = path.with_name(path.name + ".linux-shape.bak")
        rewrites = []
        if backup.exists():
            original = inspect(backup)
            current = {key: record for key, record in parsed["records"]}
            for old_key, old_record in original["records"]:
                new_key = preferred_key(old_key)
                if new_key is not None and new_key in current:
                    old_value = old_record[4 + len(old_key):]
                    new_record = current[new_key]
                    new_value = new_record[4 + len(new_key):]
                    if old_value == new_value:
                        rewrites.append({"from": old_key.decode("ascii", "replace"),
                                         "to": new_key.decode("ascii", "replace")})
        return {"path": str(path), "backup": str(backup) if backup.exists() else None,
                "keys_rewritten": len(rewrites), "key_rewrites": rewrites,
                "payload_sha256": parsed["payload_sha256"],
                "status": "already-normalized" if rewrites else "unchanged"}
    if check_only:
        return {"path": str(path), "keys_rewritten": len(parsed["aliases"]),
                "payload_sha256": parsed["payload_sha256"], "status": "would-patch"}

    ensure_no_symlink_components(path)
    backup = path.with_name(path.name + ".linux-shape.bak")
    if not backup.exists():
        shutil.copy2(path, backup)

    new_index = bytearray(parsed["index"])
    added = []
    for original, alias, record in parsed["aliases"]:
        old_len = struct.unpack_from("<I", record, 0)[0]
        # Keep the index structure and file size stable. These proven aliases
        # are same-length substitutions in the key field; record values,
        # count, footer and payload remain byte-identical.
        pos = new_index.find(record)
        if pos < 0:
            raise ValueError("record not found in index while applying key alias")
        new_index[pos + 4:pos + 4 + old_len] = alias
        added.append({"from": original.decode("ascii", "replace"),
                      "to": alias.decode("ascii", "replace")})

    rebuilt = (parsed["data"][:parsed["index_start"]] + bytes(new_index)
               + parsed["data"][parsed["index_start"] + len(parsed["index"]):])
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(rebuilt)
    shutil.copystat(path, tmp)
    tmp.replace(path)

    verified = inspect(path)
    if verified["payload_sha256"] != parsed["payload_sha256"]:
        raise RuntimeError("payload changed while patching")
    return {"path": str(path), "backup": str(backup),
            "keys_rewritten": len(added), "key_rewrites": added,
            "payload_sha256": verified["payload_sha256"], "status": "patched"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--manifest", type=Path)
    args = ap.parse_args()
    results = []
    try:
        for path in args.paths:
            result = apply(path, args.check)
            results.append(result)
            print(f"{result['status']:12s} keys={result['keys_rewritten']:2d} {path}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.manifest and not args.check:
        args.manifest.write_text(json.dumps({"format_version": 2, "bundles": results},
                                            indent=2) + "\n", encoding="utf-8")
    if args.check and any(r["status"] == "would-patch" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
