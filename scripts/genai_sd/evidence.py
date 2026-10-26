#!/usr/bin/env python3
"""Validate a FLUX image and collect provider/dispatch evidence."""

from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

from PIL import Image, ImageStat

parser = argparse.ArgumentParser()
parser.add_argument("work_dir", type=Path)
parser.add_argument("--npu-component", choices=("transformer", "unet"), default="transformer")
parser.add_argument("--vae-component", choices=("vae_decoder",), default="vae_decoder")
parser.add_argument("--width", type=int, default=1024)
parser.add_argument("--height", type=int, default=1024)
args = parser.parse_args()
root = args.work_dir.resolve()
images = sorted((root / "images").glob("*.png"))
if len(images) != 1:
    raise SystemExit(f"expected exactly one PNG, found {len(images)}")
with Image.open(images[0]) as im:
    im.load()
    if im.size != (args.width, args.height):
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

npu_model = session_for(args.npu_component)
vae = session_for(args.vae_component)
text = session_for("text_encoder")
if not npu_model or not vae:
    raise SystemExit(f"missing {args.npu_component}/VAE session records; sessions={sessions}")
for label, group in ((args.npu_component, npu_model), (args.vae_component, vae)):
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

dispatch = {args.npu_component: [], args.vae_component: [], "profiles": []}
for component, path in profile_paths:
    if not path.is_file():
        continue
    try:
        events = json.loads(path.read_text())
    except Exception as exc:
        raise SystemExit(f"cannot parse ORT profile {path}: {exc}")
    npu_events = []
    for event in events:
        event_args = event.get("args", {}) if isinstance(event, dict) else {}
        provider = str(event_args.get("provider", ""))
        if provider == "RyzenAILightExecutionProvider":
            npu_events.append({"name": event.get("name"), "cat": event.get("cat")})
    lower = (component + " " + path.name).lower()
    key = (args.vae_component if args.vae_component in lower
           else args.npu_component if args.npu_component in lower else None)
    if key:
        dispatch[key].extend(npu_events)
        dispatch["profiles"].append({"component": component, "path": str(path), "npu_events": len(npu_events)})

if not dispatch[args.npu_component] or not dispatch[args.vae_component]:
    raise SystemExit(f"NPU dispatch events not verified for both components: {dispatch}")

evidence = {
    "status": "image_generated_npu_dispatch_verified",
    "image": str(images[0]),
    "image_size": [args.width, args.height],
    "image_rgb_stddev": stat.stddev,
    "sessions": sessions,
    "dispatch": {
        "npu_component": args.npu_component,
        "npu_event_count": len(dispatch[args.npu_component]),
        "transformer_event_count": len(dispatch.get("transformer", [])),
        "vae_event_count": len(dispatch[args.vae_component]),
        "profile_files": dispatch["profiles"],
        "npu_events_sample": dispatch[args.npu_component][:5],
        "transformer_events_sample": dispatch.get("transformer", [])[:5],
        "vae_events_sample": dispatch[args.vae_component][:5],
    },
}
(root / "dispatch-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(f"Image: {images[0]} ({args.width}x{args.height})")
print(f"{args.npu_component} NPU events:", len(dispatch[args.npu_component]))
print("VAE NPU events:", len(dispatch[args.vae_component]))
