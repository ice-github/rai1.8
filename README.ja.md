# CachyOSでのRyzen AI 1.8 — ビルド・検証メモ

[English README](README.md)

このリポジトリには、**手順書・小さな補助スクリプト・ローカル変更したArch PKGBUILDのみ**を置いています。AMD公式配布物ではありません。AMDのインストーラー、SDK、wheel、共有ライブラリ、firmware、モデル重み、transaction archive、上流ソースツリーは含めていません。

## 検証結果

2026-10-25時点で、CachyOS実機1台にてビルド・検証しました。

- OS: CachyOS x86_64
- カーネル: **`7.3.0-5-cachyos`**
- CPU/NPU: AMD Ryzen AI 7 350 / in-tree `amdxdna`
- XRT: `2.25.0`（固定コミットからビルド）
- Ryzen AI 1.8 SDK quicktest、NPU列挙・基本演算を確認
- FLUX.2 klein 4Bで1024×1024画像を1枚生成
- ORTプロファイル上でTransformerのNPUイベント32件、VAEのNPUイベント4件を確認
- テキストエンコーダはCPU実行。TransformerとVAEはNPU実行

これは**単一ホストでの一時点の結果**であり、AMDやCachyOSによるサポート表明ではありません。再起動後や複数回実行の安定性は未検証です。詳細は[検証結果](docs/verification.md)を参照してください。

## 手順

1. [前提条件と安全方針](docs/prerequisites.md)
2. [XRT/SHIMの取得・ビルド](docs/build-runtime.md)
3. [隔離配置とランタイム検証](docs/runtime-checks.md)
4. [SDKの公式取得と隔離セットアップ](docs/sdk.md)
5. [FLUX.2の準備と実行](docs/flux2.md)

ローカルでビルドしたパッケージを`pacman -U`で導入する手順はありません。ユーザー所有ディレクトリに展開して使う構成です。in-treeドライバー向けの`-nokmod`構成を、別管理のカーネルモジュールと併用する場合は競合を確認してください。

## 内容

- `scripts/pkgbuild/`: XRT base/NPUおよびuserspace XDNA plugin用PKGBUILD。ローカルでビルドした上流tarballを使い、AMD/Xilinx payloadをダウンロード・同梱しません。
- `scripts/flux2/`: source準備、固定revisionモデル取得、bundle key正規化、メモリ監視、環境ラッパー、実行・検証スクリプト。
- `docs/`: 取得先、再現手順、注意点、要約した検証結果。
- `THIRD_PARTY_NOTICES.md`: 上流プロジェクトとライセンス範囲。

## ライセンス

原著作物としてライセンス可能な文書・補助コードは`LICENSE`のMIT Licenseです。PKGBUILDは固定したAMD/Xilinx上流GitリポジトリのPKGBUILDを元に変更しています。上流の著作権表示とライセンスを確認してください。SDK・モデル等の条件は各配布元が定めるもので、このリポジトリのライセンスでは変更されません。
