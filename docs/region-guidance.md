# Optional region guidance

The [README](../README.md) owns build and batch execution. Run commands below from the repository root. The advisor is off by default; enabling it does not establish model eligibility or a quality advantage. Both settings use the same engine and image.

Region guidance uses exact alpha support for isolated transparent assets, preserving the entire mark without inference. Other assets, including full-canvas background photographs, receive a bounded model proposal using a neutral-gray preview. The official renderer measures crop and occlusion losses relative to the source. Before the pixel shortlist is selected, guidance generates up to 16 alternatives from four distinct candidate methods, retaining source fit as a conservative seed. These alternatives compete later against the unchanged deterministic incumbent. When retargeting introduces visibility loss, guidance can also generate up to 16 final repairs: translate an image or overlapping group, or expand a singleton centered-cover viewport where space permits. Explicit groups and inferred source backings move together. Each evaluated proposal goes through the normal geometry, composition, text and raster checks before selection. When the selected layout has no recoverable source-relative visibility loss, alternative rendering is skipped because no proposal can satisfy the acceptance rule.

A region-based selection cannot override contract checks or measured aggregate glyph, contrast, minimum-font-size and hierarchy guards; each foreground image also retains its size floor. These proxies do not prove that every element or human-visible quality improves. When inference is needed, missing/corrupt weights, unavailable runtime, timeouts and invalid judgments retain the deterministic winner and emit an explicit fallback diagnostic. Identity cases skip inference. Guidance can now propose a repair even when the existing shortlist has no safe challenger.

At most four unique assets, two existing distinct-method challengers, 16 early proposals and 16 final repairs are examined per task; source designs over 64 elements abstain. Diagnostic rendering also abstains above 16 million pixels per canvas/asset/intermediate or 32 million cumulative element pixels, before native-size allocation. Asset judgments are cached by content, model manifest and prompt within a batch. The runtime starts lazily once per process, verifies weights, binds only to loopback and makes no external requests. HTTP requests use a 90-second socket timeout; startup polling has a 120-second deadline. These are not strict end-to-end task deadlines. These bounds are engineering choices; a timeout is a fallback, not a successful model evaluation. See [runtime and model notices](../deployment/NOTICES.txt).

The [region-repair study](../research/region-repair.txt) records four rendered component controls: visibility recovered from 33–67% to 100%, including the supplied bottle label. These are constructed failures with real rendering and guards, not held-out end-to-end wins. Public sample outputs remained unchanged. The [early region-pool study](../research/early-region-pool.txt) adds background-subject protection and proposals from outside the pixel shortlist. Rotated repairs, precise opaque-image localization and multi-step joint repairs remain limitations. The current local model is unchanged; better localization is still an experimental requirement. The new background check added about nine seconds of cold model time on the first public task in this host trial, without improving that output; this is not a MacBook benchmark.

To reproduce the semantic calibration and save actual outputs for manual review, use a new directory:

```bash
chameleon_semantic=".project-evaluation/semantic-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p .project-evaluation
docker run --rm --platform linux/amd64 --network none --cpus 8 --memory 8g \
  --entrypoint python \
  --mount "type=bind,source=$(pwd -P)/scripts,target=/app/scripts,readonly" \
  --mount "type=bind,source=$(pwd -P)/input,target=/app/input,readonly" \
  --mount "type=bind,source=$(pwd -P)/.project-evaluation,target=/app/.project-evaluation" \
  chameleon-engine scripts/evaluate_semantics.py --output-dir "$chameleon_semantic"
```

Open the generated `index.html` and `results.json`. They retain transparent/opaque asset and clear/occluded-product controls, baseline and region-guidance outputs on the public samples, region observations, abstentions, timings, process peak RSS and source/model hashes. Each condition starts a fresh model/cache; subsequent tasks in that condition reuse its runtime. Control failures are reported separately from contract failures. These are development controls, not held-out human ratings. A convincing presentation requires blinded source-family-held-out review and actual MacBook timing before claiming a visual or performance advantage.

To reproduce the repair controls and their source/before/after gallery, mount the full checkout (the harness uses development fixtures in tests/):

```bash
chameleon_repairs=".project-evaluation/region-repairs-$(date -u +%Y%m%dT%H%M%SZ)-$$"
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine scripts/evaluate_region_repairs.py --output-dir "$chameleon_repairs"
```

Use `scripts/evaluate_region_pool.py` with the same full-checkout mount and a fresh `--output-dir` to reproduce the early-pool and background-subject source/before/after controls.
