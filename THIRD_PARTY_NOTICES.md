# Third-party notices and acquisition boundaries

This repository does not contain third-party runtime, SDK, model, firmware,
or upstream source payloads. Obtain each item directly from its publisher and
review the license/terms shown at download time.

| Component | Upstream / official source | Notes |
|---|---|---|
| Ryzen AI Linux NPU XRT package | [AMD download](https://download.amd.com/opendownload/RyzenAI/Driver/RAI_1.8_Linux_NPU_XRT.zip) | AMD redistribution/license terms apply. |
| Ryzen AI Software | [AMD Ryzen AI docs](https://ryzenai.docs.amd.com/en/latest/) | Follow the Linux installation/download instructions for the 1.8 release; Ubuntu installer scripts are not assumed to work on Arch. |
| XDNA driver/SHIM | [amd/xdna-driver](https://github.com/amd/xdna-driver), pinned commit `88dda53eee336c998abca38c71d5bc79fb3633b8` | PKGBUILD adaptation; upstream repository license governs upstream portions. |
| XRT | [Xilinx/XRT](https://github.com/Xilinx/XRT), pinned submodule commit `0026185de81a179dc7d886197d3e35f9a179b4e8` | Apache-2.0 upstream. |
| FLUX.2 sd-sandbox | [amd/sd-sandbox](https://github.com/amd/sd-sandbox), pinned commit `e13ca6d7ac14fc415f8aa58acc027f427197e300` | Clone upstream yourself; no upstream source is copied here. |
| FLUX.2 klein 4B model | [Hugging Face model](https://huggingface.co/amd/FLUX.2-klein-4B-amdnpu), pinned revision `45aeffe92ecf5ce0169c511c232c2f100be3cbe1` | Review model card/license and any access terms before downloading. |
| Python dependencies | PyPI and AMD-provided wheel(s) | Their individual licenses apply. The Vitis AI ONNX Runtime wheel is not included. |

The `scripts/pkgbuild/` files are based on corresponding PKGBUILDs in the
pinned XRT and xdna-driver repositories, with local changes for CachyOS output
names, in-tree `amdxdna`, and `-nokmod` packaging. They are not the upstream
projects' official Arch packages. Preserve upstream license/copyright notices
when comparing or redistributing derivative versions.

The project `LICENSE` applies only to original material for which the
repository author can grant that license. It does not override third-party
licenses or AMD product/model terms.
