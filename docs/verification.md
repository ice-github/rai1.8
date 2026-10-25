# 実機検証記録（要約）

## 対象と結果

2026-10-25時点で、1台のCachyOS x86_64機（AMD Ryzen AI 7 350 / in-tree
`amdxdna` / XRT 2.25.0）にて以下を確認した。

- XRT pinned source build: 110 tests中108 PASS、2 SKIP、0 FAIL。
- XDNA userspace SHIM: `-release -nokmod` でbuild。
- 作成したXRT/SHIMをユーザー所有ディレクトリへ展開し、system package installなしで列挙確認。
- NPU latency / throughput / GEMMテストがPASS。標準validateの診断項目には別途未対応/skipあり。
- Ryzen AI 1.8 SDK quicktestでNPU演算を確認。
- FLUX.2 klein 4B 1024×1024画像を1枚生成。推論プロセスexit 0、画像をデコード・目視確認。
- ORT profileにTransformerのRyzenAI providerイベント32件、VAEイベント4件。
- Text encoderはCPU、TransformerとVAEはNPU providerを含むsessionで実行。
- run中のprocess tree peak RSS/PSSは約2.41/2.40 GiB、最低`MemAvailable`約9.1 GiB。これはNPUメモリを含む総システム使用量ではない。
- 実行後にhardware contextが解放され、記録時間帯に新規NPU/IOMMU kernel errorは観測されなかった。

## 限界

- 1台・1回のFLUX生成に基づく。再起動後、反復安定性、suspend/resume、他のCachyOS/kernel/firmwareでは未検証。
- Ryzen AI Software 1.8全機能の互換性を示すものではない。
- 測定時間やRSS/PSSを他機種の性能保証に使わないこと。
- 元の生ログ、画像、model/SDKファイル、ユーザー名、絶対パス、serial/PCI識別子は公開していない。

再現時は各利用者が自分のハードウェアで同じ受入条件を確認し、成功/失敗を区別して記録すること。
