# AMDから取得するファイル

この手順で必要な配布物は目的により異なる。AMDのダウンロードページでRyzen AI Software **1.8**向けであること、ライセンス・利用条件を確認してから取得する。配布物は本リポジトリに含めず、再配布もしない。

## 必須（SDK quicktestとFLUX.2を一通り再現する場合）

| ファイル | 取得元・用途 | 注記 |
|---|---|---|
| `ryzen_ai-1.8.0.tgz` | [AMD Ryzen AI Linux installation docs](https://ryzenai.docs.amd.com/en/latest/linux.html)から取得。SDK Python wheel、ORT/Vitis AI EPおよび関連runtimeのローカル隔離セットアップに使用。 | 検証時の実ファイルは約7.82 GB。AMD公開値とのchecksum照合は未記録。Ubuntu用install scriptをそのままCachyOSで実行しない。 |
| `ryzen-ai-1.8.0.exe` | AMDのRyzen AI Software 1.8配布ページから取得。FLUX用STX transaction ZIPが必要な場合に限り、アーカイブとして内容を抽出する。 | 検証時の実ファイルは約3.55 GB。**実行しない**。内包MSI/CABから必要データを取り出す。配布条件を確認し、共有・再配布しない。 |

検証時はEXEから展開したMSIのMedia/File tableでCABとの対応を確認し、次の3ファイルだけをローカル作業領域に抽出した。

| CAB | 抽出したファイル |
|---|---|
| `ryzenai_17.cab` | `sd_fastpm_DiT.zip`, `sd_fastpm_Unet.zip` |
| `ryzenai_18.cab` | `sd_preemption.zip` |

MSI tableやCABの配置・内部名は配布版で変わる可能性があるため、対象リリースの内容を照合してから抽出する。CAB全体や他のSDKファイルをGitへ追加しない。Windows installerを起動する必要はない。配布条件が抽出・利用を認めることを利用者自身が確認すること。

## このソースビルド手順では不要（任意の代替経路）

| ファイル | 用途 | この手順での扱い |
|---|---|---|
| [`RAI_1.8_Linux_NPU_XRT.zip`](https://download.amd.com/opendownload/RyzenAI/Driver/RAI_1.8_Linux_NPU_XRT.zip) | AMD配布のLinux XRT/NPU runtime bundle | 今回のXRT/SHIMは固定した公開Git sourceからビルドしたため必須ではない。AMD配布バイナリを使う別経路を選ぶ場合のみ必要。 |

## AMD公開GitHubから取得するsource

以下は配布archiveとは別に、固定revisionを上流からcloneする。ソースツリーはこのリポジトリに含めない。

| Repository | Revision | 用途 |
|---|---|---|
| [`amd/xdna-driver`](https://github.com/amd/xdna-driver)（recursive submodules含む） | `88dda53eee336c998abca38c71d5bc79fb3633b8` | SHIMとXRT submoduleのbuild |
| [`amd/sd-sandbox`](https://github.com/amd/sd-sandbox) | `e13ca6d7ac14fc415f8aa58acc027f427197e300` | FLUX runner source |

XRT submoduleは`0026185de81a179dc7d886197d3e35f9a179b4e8`に固定される。FLUXモデルはAMD配布archiveではなく、[Hugging Face上のAMD model repository](https://huggingface.co/amd/FLUX.2-klein-4B-amdnpu)からrevision `45aeffe92ecf5ce0169c511c232c2f100be3cbe1`を取得する。モデルカードとライセンス条件を確認すること。

### ストレージ計画

SDK tarballに加えてWindows EXEを一時保管する場合、ダウンロードだけで約11.4 GB必要です。展開後のSDK venv/model/build領域を含む目安は[ストレージ表](prerequisites.md#ストレージ)を参照してください。アーカイブも残す場合は追加容量を見込んでください。
