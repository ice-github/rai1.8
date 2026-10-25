#!/usr/bin/env python3
"""Validate a FLUX image and collect provider/dispatch evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageStat

root = Path(sys.argv[1]).resolve()
images = sorted((root / "images").glob("*.png"))
if len(images) != 1:
    raise SystemExit(f"expected exactly one PNG, found {len(images)}")
with Image.open(images[0]) as im:
    im.load()
    if im.size != (1024, 1024):
        raise SystemExit(f"wrong image dimensions: {im.size}")
    stat = ImageStat.Stat(im.convert("RGB"))
    if max(stat.stddev) < 2.0:
        raise SystemExit("image appears nearly uniform; refusing success")

session_file = root / "sessions.jsonl"
if not session_file.exists():
    raise SystemExit("session provider evidence is missing")
sessions = [json.loads(line) for line in session_file.read_text().splitlines() if line.strip()]
def session_for(name: str):
    matches = [s for s in sessions if name in str(s.get("model_file", "")).lower()]
    if not matches:
        matches = [s for s in sessions if name in str(s.get("component", "")).lower()]
    return matches

transformer = session_for("transformer")
vae = session_for("vae_decoder")
text = session_for("text_encoder")
if not transformer or not vae:
    raise SystemExit(f"missing Transformer/VAE session records; sessions={sessions}")
for label, group in (("Transformer", transformer), ("VAE", vae)):
    if not any("RyzenAILightExecutionProvider" in s.get("providers", []) for s in group):
        raise SystemExit(f"{label} session did not include RyzenAILightExecutionProvider")
if text and not any("CPUExecutionProvider" in s.get("providers", []) for s in text):
    raise SystemExit("text encoder session did not use CPUExecutionProvider")

profile_paths = []
profile_list = root / "profile-files.jsonl"
if profile_list.exists():
    for line in profile_list.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("profile"):
                p = Path(record["profile"])
                if not p.is_absolute():
                    p = Path.cwd() / p
                profile_paths.append((record.get("component", ""), p))
if not profile_paths:
    profile_paths = [(p.name, p) for p in (root / "profiles").glob("*.json")]

dispatch = {"transformer": [], "vae_decoder": [], "profiles": []}
for component, path in profile_paths:
    if not path.is_file():
        continue
    try:
        events = json.loads(path.read_text())
    except Exception as exc:
        raise SystemExit(f"cannot parse ORT profile {path}: {exc}")
    npu_events = []
    for event in events:
        args = event.get("args", {}) if isinstance(event, dict) else {}
        provider = str(args.get("provider", ""))
        if provider == "RyzenAILightExecutionProvider":
            npu_events.append({"name": event.get("name"), "cat": event.get("cat")})
    lower = (component + " " + path.name).lower()
    key = "vae_decoder" if "vae" in lower else "transformer" if "transformer" in lower else None
    if key:
        dispatch[key].extend(npu_events)
        dispatch["profiles"].append({"component": component, "path": str(path), "npu_events": len(npu_events)})

if not dispatch["transformer"] or not dispatch["vae_decoder"]:
    raise SystemExit(f"NPU dispatch events not verified for both components: {dispatch}")

evidence = {
    "status": "image_generated_npu_dispatch_verified",
    "image": str(images[0]),
    "image_size": [1024, 1024],
    "image_rgb_stddev": stat.stddev,
    "sessions": sessions,
    "dispatch": {
        "transformer_event_count": len(dispatch["transformer"]),
        "vae_event_count": len(dispatch["vae_decoder"]),
        "profile_files": dispatch["profiles"],
        "transformer_events_sample": dispatch["transformer"][:5],
        "vae_events_sample": dispatch["vae_decoder"][:5],
    },
}
(root / "dispatch-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(f"Image: {images[0]} ({Image.open(images[0]).size[0]}x1024)")
print("Transformer NPU events:", len(dispatch["transformer"]))
print("VAE NPU events:", len(dispatch["vae_decoder"]))
