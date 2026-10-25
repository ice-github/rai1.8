# 前提条件と安全方針

## 対象

- Arch系/CachyOS x86_64。記録した実機は CachyOS、in-tree `amdxdna`、Ryzen AI 7 350。
- `/dev/accel/accel0` が存在し、作業ユーザーから読み書きできること。
- 空きメモリ、swap、ビルド用ディスク容量を作業前に確認すること。XRTビルドとSDK/モデル取得には大きな空き容量が必要。
- `git`, `base-devel`, CMake/Ninja、C/C++ compiler、Python 3.12環境、`uv`、`fish`（任意）、`patchelf`/`readelf`等を利用する。
- 実機検証前に `/dev/accel`、カーネルドライバー、firmware、Secure Boot/権限設定を確認する。

実機記録と同一の結果を保証するものではない。カーネル、firmware、BIOS、依存パッケージの差は結果に影響する。

## ストレージ

検証時の`cachyos/`作業領域は合計約47 GiBでした（`du -sh`の丸め値）。内訳の目安:

| データ | 実測使用量 |
|---|---:|
| SDK展開物＋SDK venv | 約31.4 GiB（7.4 + 24 GiB） |
| FLUX.2一式 | 約13 GiB（モデル約8 GiB、専用venv約4 GiBが中心） |
| XRT/SHIM source/build、残りの検証ファイル | 約2.4 GiB（合計からの概算） |
| 隔離runtime | 約0.23 GiB |
| **合計** | **約47 GiB** |

ゼロから同じ一式を作る場合、取得アーカイブや展開・ビルド中の一時コピー分として**最低60〜70 GiBの空き容量**を推奨します。ダウンロード物や複数のビルドツリーを残す場合は追加容量が必要です。数値は単一環境の実測・概算で、厳密な最小要件ではありません。

## 非破壊の原則

- 専用のユーザー所有ディレクトリを作り、その下にsource/build/runtime/sdk/flux2を隔離する。
- この手順は `pacman -U`、`sudo make install`、DKMS有効化、カーネルモジュールの入替え、`/opt`・`/etc`・シェル設定の書換えを行わない。
- CachyOSではXRT上流の `xrtdeps.sh` がOS flavor判定に失敗する既知問題がある。ビルド依存は確認してからpacmanで導入する。これはシステムパッケージ変更なので、実行内容を確認しユーザー自身が承認する。
- SDK配布物は公式配布条件に従い、Windows installer/EXEは起動せず、Linux向け配布物を使う。FLUX transaction dataがWindows CAB内にしかないリリースでは、CABから必要データだけをローカル抽出し、抽出物を再配布しない。
- 公開リポジトリへは、自作コード・PKGBUILD・手順・一般化した要約だけを追加する。vendor package、wheel、共有ライブラリ、firmware、モデル、生成画像、venv、cache、build成果物、生ログは追加しない。

## ピン留め

| 対象 | Revision |
|---|---|
| amd/xdna-driver | `88dda53eee336c998abca38c71d5bc79fb3633b8` |
| XRT submodule | `0026185de81a179dc7d886197d3e35f9a179b4e8` |
| amd/sd-sandbox | `e13ca6d7ac14fc415f8aa58acc027f427197e300` |
| FLUX.2 model | `amd/FLUX.2-klein-4B-amdnpu` @ `45aeffe92ecf5ce0169c511c232c2f100be3cbe1` |

AMD download URLs and terms can change. Verify checksums against publisher information where available; do not treat a locally recorded hash as an official AMD checksum.
