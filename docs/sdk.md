# Ryzen AI SDK 1.8 — 公式取得と隔離セットアップ

AMD SDK/EP binaries are not redistributed here. Start from the [official AMD
Linux installation instructions](https://ryzenai.docs.amd.com/en/latest/linux.html)
and obtain the Ryzen AI Software 1.8 Linux package under AMD's current terms.
Verify publisher-provided checksums/signatures if available. Do not assume the
Ubuntu installation shell script is suitable for CachyOS: inspect it first;
the tested workflow did not run that script because it contains Ubuntu/apt/dpkg
assumptions and global-path behavior.

## Isolated layout

Use a Python 3.12 interpreter and an isolated venv under the user work root:

```bash
WORK="$HOME/rai18-work/cachyos"
mkdir -p "$WORK/sdk/dist" "$WORK/sdk/libcompat"
uv venv --python 3.12 "$WORK/sdk/venv"
```

Safely inspect the downloaded archive before extraction (`tar -tf`; reject
absolute paths and `..` components). Extract to `$WORK/sdk/dist`, inspect the
vendor install script and wheel list, then follow the AMD release's documented
installation order manually into the venv. Do not copy SDK libraries into
`/usr`, `/opt`, or the repository. Install vendor wheels using their supplied
filenames and documented prerelease/dependency flags; the exact filenames are
release-specific. Record `pip freeze` and hashes locally.

The verified environment needed the vendor Vitis AI ONNX Runtime wheel and
RyzenAI GenAI runtime payloads. Those files are intentionally absent from this
repository. `scripts/flux2/requirements.txt` is a reference for Python-side
versions, not a self-contained lockfile: install the vendor ORT wheel from the
official SDK distribution rather than assuming it is a public PyPI package.

Common CachyOS-specific diagnostics from the one-host test:

- If an SDK ELF requests an executable stack and the hardened loader rejects
  it, inspect that exact ELF. Do not patch every shared object blindly; preserve
  a local backup and document the change.
- If the EP needs `libncurses.so.6` but CachyOS only provides the wide SONAME,
  use a private compatibility link in the user work tree only after verifying
  ABI compatibility. Never add a system-wide link.
- Put the matching XRT libraries before vendor `voe/lib` in
  `LD_LIBRARY_PATH` to avoid accidentally loading the SDK's older XRT SONAME.
- Keep SDK and FLUX virtual environments separate. Do not mix Python ABIs.

Run the SDK vendor quicktest only after checking its invocation and confirming
that logs indicate NPU execution rather than CPU fallback. Record versions,
exit code, provider and event evidence without publishing proprietary logs.
