# GenAI-SD runtime tooling

`scripts/genai_sd/` is the source of truth for model/runtime preparation,
GenAI-SD compatibility helpers, CPU T5 precomputation, inference execution,
and RyzenAI execution evidence. It has no dependency on the frontend project.

The frontend may provision this directory into the private runtime tree, but a
deployed application invokes that runtime copy and does not require this
submodule checkout to remain available.

## CLI protocol v1

Set `PYTHONPATH` to the directory containing `genai_sd/` and use the runtime's
Python environment:

```bash
python -m genai_sd.cli --protocol-version
python -m genai_sd.cli run --request request.json --result result.json
python -m genai_sd.cli validate --request validation-request.json --suite suite.json
```

Requests are JSON objects with `protocol_version: 1`. Empty negative prompts
must be represented as the empty string, never omitted or replaced with a
sample prompt. A successful result means the image passed validation and the
Transformer/UNet and VAE have real RyzenAI EP profile events. It does not by
itself authorize a web application to expose a model; that remains an
application-level decision.

The SD3 validation request contains the pinned model and CPU T5 revisions, the
prepared-model manifest/hash, and the fixed four-case matrix. Validation runs
under the same filesystem lock as ordinary inference. A successful suite is
evidence only; the frontend separately decides whether to activate its model
lock.

Provision the official CPU T5-only files into the ignored runtime model area
with the pinned downloader:

```bash
python scripts/genai_sd/provision_cpu_t5.py \
  /path/to/runtime/flux2/models/shared_t5_v1_1_xxl_cpu
```

The package's offline tests run with:

```bash
PYTHONPATH=scripts pytest -q tests/genai_sd
```
