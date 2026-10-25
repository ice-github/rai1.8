# Ryzen AI 1.8 on CachyOS — community build and validation notes

This repository contains **instructions, small helper scripts, and locally
adapted Arch PKGBUILDs only**. It is not an AMD distribution and does not
include or redistribute AMD installers, SDKs, wheels, libraries, firmware,
model weights, transaction archives, or upstream source trees.

[日本語版 README](README.ja.md)

Documentation and scripts are primarily Japanese, matching the original
validation notes. Contributions and corrections are welcome.

## What was validated

On one CachyOS system (**kernel `7.3.0-5-cachyos`**) with an in-tree
`amdxdna` driver and Ryzen AI 7 350, XRT/SHIM built from the pinned sources, NPU enumeration/basic tests, the Ryzen
AI SDK quicktest, and one FLUX.2 klein 4B image generation were verified.
ORT profiles showed NPU events for Transformer (32) and VAE (4); the text
encoder ran on CPU. This is a **single-host, point-in-time result**, not an
AMD/CachyOS support statement. Reboot and repeated-run stability tests remain
unverified. See [validation](docs/verification.md).

| Timing (single run) | Duration |
|---|---:|
| End-to-end process | 21.233 s |
| Pipeline execution | 11.553 s |
| Model-load summary: CPU / NPU | 0.88 s / 4.59 s |

Per-component model-load timings and measurement caveats are in the [Japanese
validation record](docs/verification.md#処理時間の内訳).

## Start here

1. Read [prerequisites and safety](docs/prerequisites.md).
2. Follow [runtime build](docs/build-runtime.md), then [isolated runtime checks](docs/runtime-checks.md).
3. For the SDK, follow [official acquisition and isolated setup](docs/sdk.md).
4. For FLUX.2, follow [model/source preparation and inference](docs/flux2.md).

No step requires installing the locally built packages with `pacman -U`.
The documented runtime can be unpacked under a user-owned work directory.
Do not install the in-tree-driver (`-nokmod`) setup alongside an independently
managed kernel module without reviewing conflicts first.

## Repository contents

- `scripts/pkgbuild/`: CachyOS-oriented PKGBUILDs for XRT base, NPU, and the
  userspace XDNA plugin. They consume locally built upstream tarballs; they do
  not download or bundle AMD/Xilinx payloads.
- `scripts/flux2/`: source preparation, pinned model downloader, bundle-key
  normalization, memory monitor, environment wrappers, runner, and verifier.
- `docs/`: acquisition links, reproducible commands, caveats, and summarized
  evidence.
- `THIRD_PARTY_NOTICES.md`: upstream links and licensing boundaries.

## Licensing

Original documentation and helper code are MIT-licensed (see `LICENSE`). The
PKGBUILDs are adaptations of files from the pinned AMD/Xilinx upstream Git
repositories; retain their original notices and consult the upstream licenses
listed in `THIRD_PARTY_NOTICES.md`. SDK/model/software terms are supplied by
their respective publishers and are not relicensed by this repository.
