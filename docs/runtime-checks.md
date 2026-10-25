# 隔離配置とランタイム検証

生成した3つの `.pkg.tar.zst` は**インストールせず**、監査後にローカル
runtime rootへ展開する。衝突ファイルがあれば停止し、上書きで回避しない。

```bash
RUNTIME="$HOME/rai18-work/cachyos/runtime"
mkdir -p "$RUNTIME"
for pkg in /path/to/xrt-{base,npu}-*.pkg.tar.zst /path/to/xrt-plugin-amdxdna-*.pkg.tar.zst; do
  while IFS= read -r entry; do
    case "$entry" in /*|../*|*/../*) echo "unsafe package path: $entry" >&2; exit 1;; esac
  done < <(bsdtar -tf "$pkg")
  bsdtar -xpf "$pkg" -C "$RUNTIME"
done
```

Extraction paths and package formats should be reviewed before extraction.
Keep a package manifest/hash list locally. The runtime environment is expected
at `$RUNTIME/opt/xilinx/xrt`; it does not register system OpenCL ICDs.

For a shell session, set paths explicitly (fish users can adapt syntax):

```bash
export XILINX_XRT="$HOME/rai18-work/runtime/opt/xilinx/xrt"
export PATH="$XILINX_XRT/bin:$PATH"
export LD_LIBRARY_PATH="$XILINX_XRT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

Then check in order:

```bash
type -a xrt-smi
ldd "$XILINX_XRT/bin/xrt-smi" | grep 'not found' && exit 1 || true
LC_ALL=C LANGUAGE=C "$XILINX_XRT/bin/xrt-smi" --version
LC_ALL=C LANGUAGE=C "$XILINX_XRT/bin/xrt-smi" examine --batch
LC_ALL=C LANGUAGE=C "$XILINX_XRT/bin/xrt-smi" examine -r all --batch
```

NPU enumeration is not proof of execution. Consult the pinned XRT test help,
run latency/throughput/GEMM and the standard validation separately, and capture
exit status plus before/after kernel log/context state. Interpret unsupported
diagnostic queries separately from failed computations. Never claim all tests
passed when upstream tests were skipped.

No reboot, suspend, module reload, or system install is automated by this
repository.
