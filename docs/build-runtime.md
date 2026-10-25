# XRT / XDNA SHIM の取得・ビルド・パッケージ

このリポジトリはソースを同梱しません。固定コミットを上流から取得します。

## 1. source取得

```bash
mkdir -p "$HOME/rai18-work/src" "$HOME/rai18-work/build" "$HOME/rai18-work/cachyos/runtime"
cd "$HOME/rai18-work/src"
git clone --recurse-submodules https://github.com/amd/xdna-driver.git
cd xdna-driver
git checkout 88dda53eee336c998abca38c71d5bc79fb3633b8
git submodule update --init --recursive
test "$(git -C xrt rev-parse HEAD)" = 0026185de81a179dc7d886197d3e35f9a179b4e8
```

Review the upstream build scripts and their effects before building. Do not use
the upstream kernel-module/DKMS path for this in-tree-driver recipe.

## 2. dependencies and XRT

Install the documented Arch/CachyOS build dependencies after reviewing the
package list. Do not run `xrtdeps.sh` on CachyOS: the pinned script identifies
`ID=cachyos` as an unknown OS flavor. The exact package list may change with
the OS release; consult upstream XRT build docs and inspect `build.sh`.

```bash
cd "$HOME/rai18-work/src/xdna-driver/xrt/build"
LC_ALL=C LANGUAGE=C ./build.sh -npu -opt -j "${JOBS:-4}"
ctest --test-dir build --output-on-failure
```

Use a conservative job count based on available RAM. For deterministic text
output from tests, set `LC_ALL=C LANGUAGE=C`. Record test pass/skip/fail counts;
do not report skipped tests as passes.

## 3. userspace SHIM only

```bash
cd "$HOME/rai18-work/src/xdna-driver/build"
./build.sh -release -nokmod -j "${JOBS:-4}"
```

`-nokmod` is intentional: CachyOS provides the in-tree `amdxdna` driver. Do not
run the DKMS build or installer hooks as part of this recipe.

## 4. build Arch packages without installing them

Copy the three PKGBUILDs from this repository into separate package directories.
Build products remain in the local work tree, not in this Git repository.

```bash
REPO=/path/to/rai1.8
mkdir -p "$HOME/rai18-work/pkgbuild"/{xrt-base,xrt-npu,xrt-plugin-amdxdna}
cp "$REPO/scripts/pkgbuild/xrt-base/PKGBUILD" "$HOME/rai18-work/pkgbuild/xrt-base/"
cp "$REPO/scripts/pkgbuild/xrt-npu/PKGBUILD" "$HOME/rai18-work/pkgbuild/xrt-npu/"
cp "$REPO/scripts/pkgbuild/xrt-plugin-amdxdna/PKGBUILD" "$HOME/rai18-work/pkgbuild/xrt-plugin-amdxdna/"
```

Point `XRT_BUILD_DIR` at the XRT `Release` directory and `XDNA_BUILD_DIR` at
the SHIM `Release` directory. Check that each expected tarball exists before
building. Example (adjust package path to your checkout):

```bash
XRT_BUILD_DIR="$HOME/rai18-work/src/xdna-driver/xrt/build/Release" \
  makepkg --cleanbuild --nodeps -p "$HOME/rai18-work/pkgbuild/xrt-base/PKGBUILD"
XRT_BUILD_DIR="$HOME/rai18-work/src/xdna-driver/xrt/build/Release" \
  makepkg --cleanbuild --nodeps -p "$HOME/rai18-work/pkgbuild/xrt-npu/PKGBUILD"
XDNA_BUILD_DIR="$HOME/rai18-work/src/xdna-driver/build/Release" \
  makepkg --cleanbuild --nodeps -p "$HOME/rai18-work/pkgbuild/xrt-plugin-amdxdna/PKGBUILD"
```

`makepkg` commonly expects its PKGBUILD in the current directory; if your
version rejects `-p` with absolute paths, `cd` into each package directory and
run it there while exporting the same variables. Review generated package
contents with `bsdtar -tf` before use. Confirm no kernel modules, firmware,
DKMS scripts, or install hooks are present. This project intentionally does
not provide a `pacman -U` command.

## Known PKGBUILD adaptations

- XRT CPack output names may include CachyOS `VERSION_ID`; base/NPU PKGBUILDs
  glob the release tarball rather than assuming an exact filename.
- `-nokmod` SHIM packaging omits DKMS/kernel-header dependencies and module
  install hooks. `!strip` protects XRT SMI VTD archives from stripping.
- Package scripts set group/world write bits off in the package staging tree.

These packaging files are derived from upstream PKGBUILDs; see
`THIRD_PARTY_NOTICES.md`.
