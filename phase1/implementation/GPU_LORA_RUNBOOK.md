# Optional GPU LoRA pipeline — PREPARATION ONLY / DISABLED

No downloads, GPU provisioning, paid services, training, merges, conversions or model promotion have been executed. `../GPU_LORA_PLAN.json` remains disabled. `LoRARecipe` validates gates/paths; it is not a training executor. All actual GPU/training/conversion acceptance checks remain gated, not inferred from source code.

## Separate approvals, in order
1. Review base model identity/license and exact immutable revision; separately approve the weight download and its storage location. Candidate original full-precision release: Qwen/Qwen2.5-1.5B-Instruct. This is a candidate, not proof it reproduces the existing GGUF: compare architecture, tokenizer, special tokens, chat template, metadata and revision, and stop on mismatch. Never train from the existing quantized GGUF or load the 9B derivative.
2. Review selected non-personal/synthetic JSONL, consent manifest hash, successful-interaction proof, manual PII/secret review, license, revocations and grouped train/validation/test split hashes. No real personal data or cloud upload is currently approved. GPU use off-device is a data transfer and needs its own approval even if the GPU is called 'private'.
3. Approve a specific GPU host, access method, budget and termination limit. Host, storage, CUDA/runtime and dependencies are currently unselected/unverified. No credential transfer is part of this pipeline.
4. On that approved host, make a versioned environment lock (Python, PyTorch, CUDA, transformers, peft, accelerate, datasets, tokenizer libraries and chosen trainer; bitsandbytes only if separately choosing QLoRA). Record resolved versions, wheel/artifact hashes and `pip freeze`. Do not call this ready before the synthetic smoke tests pass. No invented compatible-version claims are made.
5. Approve the actual synthetic training pilot, then independently review held-out evaluation before any larger run. Downloads/GPU approval alone is not training approval.

## Immutable run layout
Choose a new unique run directory; creation fails if it already exists:

    runs/<version>/manifest.json
    runs/<version>/dependencies.lock
    runs/<version>/base-manifest.json
    runs/<version>/consent-manifest.json
    runs/<version>/data/{train,validation,test}.jsonl
    runs/<version>/adapter/
    runs/<version>/evaluation/{base-hf,adapter-hf,merged-hf,f16-gguf,q4-gguf}.json
    runs/<version>/merged-fp/
    runs/<version>/model-f16.gguf
    runs/<version>/model-q4_k_m.gguf

Manifest records original base repository + revision + license + tokenizer/template hashes, runtime/dependency hashes, dataset/split/consent hashes, correction-family grouping, source code hash, seed, hyperparameters, target modules, model/adapter hashes, metrics and all approvals. Keep external consent/source identifiers outside messages-only training JSONL. Old run versions and the original phone GGUF are never overwritten.

## Trainer preparation to validate on approved hardware
- Initial proposal only: seed 42, rank 8, alpha 16, dropout 0.05, sequence length 512. Final effective batch, precision, learning rate/steps and target modules are unselected until resource and architecture checks; no guessed target-layer names are accepted.
- Load the compatible original full-precision HF model and its matching tokenizer. Derive the chat template from the pinned base manifest. If using QLoRA, perform supported quantized loading inside the chosen trainer; do not substitute GGUF for HF weights.
- Use an assistant-only loss mask generated from actual tokenizer offsets/role markers. Verify token IDs and mask values on multi-turn synthetic samples: user/system/template/padding tokens masked; intended assistant completion tokens unmasked. Abort for missing/ambiguous template markers, packing across unrelated examples, truncation that removes a target or an empty target mask.
- Freeze held-out splits before training. Corrections from the same interaction, exact/near duplicates and common source families must remain in one split. The current n-gram/family grouping is conservative, not a guarantee against semantic paraphrase leakage; manually check held-out records.
- Train only adapters, never mutate base weights in place. The first pilot uses synthetic data and approved bounded steps/resources, with no evaluation-driven reuse of held-out test examples for training.

## Evaluation gates, chosen BEFORE the run
Required paired runs use identical prompts/templates, decoding settings and untouched held-out records. Retain raw outputs only in the approved location and store bounded, redacted reports.
- Instruction following: exact/assertion checks with actual outputs; quality degradation no worse than an agreed threshold (current conservative proposal: two percentage points).
- Source attribution: distinguish user statements, assistant drafts, reported claims and disputed claims; do not turn old assistant text into verified memory.
- Accepted corrections: held-out corrections improve without source leakage.
- Refusal/project isolation: no access to another project or ungranted record.
- Secret canaries and privacy: zero detected leaks; privacy/source/isolation regressions block promotion regardless of average quality.
- General quality: blind or deterministic held-out comparison, not cherry-picked training examples.
- Failed/partial/interrupted training or evaluation remains a failed/deferred run. No automatic retry/spend or promotion.

## Conversion order (not executed)
1. Validate adapter-HF against base-HF before merging.
2. Load an untouched copy of the approved original FP model, attach the approved adapter, merge into the NEW `merged-fp/` directory and validate it. Never merge into the base download directory or overwrite the phone model.
3. Use a pinned, compatible llama.cpp converter on that NEW merged directory to create NEW F16 GGUF. Record converter revision/arguments/hash.
4. Quantize that NEW F16 file to NEW Q4_K_M with a pinned compatible quantizer. Record quantizer revision/arguments/hash.
5. Validate both files, tokenizer/chat-template equivalence, actual generation/attribution/privacy/quality, and stop on conversion errors. HF success does not establish converted-GGUF success.
6. Obtain separate human promotion approval with exact version/hashes/metrics and a model-selection rollback. No app setting, Ollama model, Qwen server or existing GGUF is changed automatically.

## Rollback
Until separate promotion approval the served model selection never changes, so rollback is simply leaving the existing served model selection unchanged and retaining the unpromoted version for review. After any future promotion, switch only the approved selection back to the previously verified original hash and verify generation using the established endpoint. Do not delete the failed adapter, consent/evaluation manifests or history; mark it rejected/revoked. If a dataset consent is revoked, invalidate future builds containing it and retain auditable version lineage. A file already exported cannot be recalled by a local flag.
