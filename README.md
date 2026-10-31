# Chameleon

An offline design-retargeting engine for the Adobe University Hackathon. Given a source design and target canvas, it produces one adapted design JSON and a PNG through the supplied official renderer. It preserves every element ID, literal text, font family and image asset, and selects the result automatically.

## Build and run

Use Bash on Linux, macOS or WSL with a running Docker Linux-container engine. Run from this repository’s root (the directory containing this README and Dockerfile). The build needs internet access; execution does not. No host Python packages, API keys, GPU or external model service are required.

The build downloads dependencies and **1,949,063,104 bytes of model weights**, even when inference is disabled. Allow additional disk space for the runtime, image and build layers. Stage one runs the engine directly; Adobe Express is not needed.

```bash
docker version
docker build --platform linux/amd64 -t chameleon-engine .
mkdir -p output
docker run --rm --platform linux/amd64 --network none \
  -e CHAMELEON_ADVISOR=off \
  --mount "type=bind,source=$(pwd -P)/input,target=/app/input,readonly" \
  --mount "type=bind,source=$(pwd -P)/output,target=/app/output" \
  chameleon-engine 2>output/run.log
```

On Apple Silicon, Docker must support linux/amd64 emulation. The container uses CPU execution; host Metal acceleration is not assumed. Native MacBook/reference-machine performance has not been measured. The captured rules name Apple M5 Pro but leave exact CPU/RAM/disk limits unresolved.

The included three sample tasks should produce three JSON/PNG pairs and exit with status 0. Inspect the PNGs at their native size. The advanced sample deliberately references missing `solstice_holiday_badge_2025.png`; the renderer’s placeholder is expected. Do not add a replacement asset.

### Run another input set

Each top-level `*.json` file is one task containing `source: {canvas, elements}` and `target_canvas: {width, height}`. Subdirectories are not scanned. See the [schema](chameleon_design_schema_v0.9.json) and [sample](input/chameleon_sample_level1_warmup.json).

The following command works with the included files. Change the first three variables to absolute paths for another input set and its original assets/fonts. All source directories must already exist. Asset filenames must match the tasks’ `asset_id` values; replacing only the JSON input does not supply new images or fonts.

```bash
chameleon_inputs="$(pwd -P)/input"
chameleon_assets="$(pwd -P)/brand_kit/assets"
chameleon_fonts="$(pwd -P)/brand_kit/fonts"
mkdir -p output
chameleon_output="$(mktemp -d "$(pwd -P)/output/benchmark.XXXXXX")"
docker run --rm --platform linux/amd64 --network none \
  -e CHAMELEON_ADVISOR=off \
  --mount "type=bind,source=$chameleon_inputs,target=/app/input,readonly" \
  --mount "type=bind,source=$chameleon_assets,target=/app/brand_kit/assets,readonly" \
  --mount "type=bind,source=$chameleon_fonts,target=/app/brand_kit/fonts,readonly" \
  --mount "type=bind,source=$chameleon_output,target=/app/output" \
  chameleon-engine 2>"$chameleon_output/run.log"
```

Results are in `$chameleon_output`. Use a fresh output directory for each benchmark and keep it separate from the inputs. Reusing a directory replaces matching pairs but leaves unrelated results from earlier runs.

For each successful `<task>.json`, the runner writes `<task>_output.json` and `<task>_output.png`. Output JSON contains only the adapted design. Task failures remove that task’s stale output pair, record the error and allow later tasks to run. Any task failure or an empty input directory produces a nonzero exit status.

`run.log` contains one runner JSON record per task, including timings, warnings and layout diagnostics. Native dependencies may also write plain-text warnings to stderr, so the whole log is not a strict JSONL file. A valid design and real PNG are required; there is no fallback that replaces the design with labeled boxes.

## Approach

Chameleon treats design retargeting as a constrained layout search. It uses the source design to infer which elements belong together, generates arrangements for the target canvas, and selects one automatically. The objective is to preserve the design's identity and hierarchy while keeping its content readable as the aspect ratio changes.

The default pipeline has five stages:

1. **Measure the source.** Measure text with the supplied fonts and identify the visible extent of transparent images. Combine explicit groups and inferred relationships, such as text on a backing rectangle, into internal layout units. These units guide placement without changing the submitted element IDs or group memberships.
2. **Generate alternatives.** Start with a layout that fits the original composition to the target. Explore rows, columns, split panels, arrangements of headlines and images, and repeated-card layouts where the source structure supports them. Search budgets and pruning limit the number of size and placement combinations evaluated.
3. **Compare valid layouts.** Reject candidates that violate the output contract. Rank the remaining candidates using text size, hierarchy, alignment, grouping, image prominence, and deviation from the source composition. Render a small shortlist to measure contrast and visual busyness. The valid source-fit candidate stays in this comparison as a baseline.
4. **Repair weak results.** When the selected layout has tiny text, overflow, or excessive overlap, try additional flow and grid arrangements. Targeted refinements can enlarge text and compact text panels; a wider search can revisit layouts when text remains too small. Each pass applies its own preservation and quality guards before accepting an improvement over the current result.
5. **Validate and export.** Independently check element conservation, literal text, font families, assets, styles, and rotated canvas bounds. Render the selected design through the pinned official converter and renderer, then verify the PNG format and dimensions before publishing the output pair.

Optional **region guidance** adds subject awareness to this search. Transparent assets use their visible alpha bounds; a local vision-language model proposes subject regions for other images. These regions guide additional layout candidates and repairs aimed at reducing cropping or occlusion. Renderer-based visibility measurements and deterministic guards control acceptance. The model does not write the final design or generate replacement imagery; setup and eligibility limitations are described below.

There is one production engine and one selected result per task. The search is bounded, and its scores are engineering heuristics rather than Adobe's scoring formula or a guarantee of visual quality. The engine preserves styles, group IDs, stacking order, and strict canvas bounds as conservative policies. For the detailed selection rules and visual review workflow, see [development and evaluation](docs/development.md#how-selection-worksand-its-limits).

## Dependencies and optional model

The Dockerfile pins Python 3.11 by image digest. [requirements.lock.txt](requirements.lock.txt) pins 41 Python dependencies, including `cr-renderer` at `a17e1fb9a732959dd6c21ae168d5ee09d74bd64f`. Supplied fonts/assets and the unchanged converter are included. System packages resolve at build time; a cache-assisted build is not a guarantee of future byte-identical images.

The image also includes CPU `llama.cpp` at `889f2ec96deacbc2d8a9a67dbe181eaa43a2fb3b` and unmodified public **Qwen3.5-2B Q4_K_M**, with an F16 vision projector. [deployment/model.json](deployment/model.json) records immutable download URLs, revisions, file sizes and verified SHA-256 hashes. The two weight files total **1,949,063,104 bytes**; allow additional disk space for the runtime, image and build layers. See the [licenses and notices](deployment/NOTICES.txt). No fine-tuned adapter is used.

| Setting | Behavior |
| --- | --- |
| `CHAMELEON_ADVISOR=off` (default) | Deterministic layout search; no model inference. |
| `CHAMELEON_ADVISOR=regions` | Exact alpha-region guidance for transparent assets and bounded local vision-language inference for other assets; renderer-measured visibility and safety checks control acceptance. |

To enable guidance, replace `-e CHAMELEON_ADVISOR=off` with `-e CHAMELEON_ADVISOR=regions` in either run command. Identity cases can bypass guidance; failures/timeouts retain the deterministic result with a diagnostic. Model requests use only loopback inside the network-isolated container. No hosted API is used.

**Disabling inference does not remove the weights or runtime from the image, or skip their build-time download.** The approved-model list and size cap were not supplied in the captured organizer material. Public availability and licensing do not prove eligibility. The default remains off while eligibility and independent visual benefit are unresolved. [Region-guidance details](docs/region-guidance.md) cover limits, caching, fallback behavior and reproducible controls.

Our resource trial used `--cpus 8 --memory 8g`; these are local measurement settings, not organizer requirements. The captured [submission rules](RULES.md) specify no hard stage-one execution-time cutoff, but speed, reliability and the actual reference machine still matter.

## Verification and limitations

The latest regression run passed all 211 Python tests and five review-note JavaScript tests. Coverage includes effective text-style colors, malformed model responses, numeric input representations, subpixel image proportions and review-harness failure handling. The latest production runtime is unchanged from the verified offline public runs with guidance off and on; all six JSON/PNG pairs matched the prior release. Fresh mixed valid/invalid batches verified failure isolation and stale-output cleanup in both modes. See [submission readiness](docs/submission.md) for the verification record and remaining external checks.

To test current source against the built runtime:

```bash
docker run --rm --platform linux/amd64 --network none \
  -e CHAMELEON_ADVISOR=off --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine -m unittest discover -s tests
```

This mount tests the checkout; the build/run command above tests baked production code. Development tests and scripts are excluded from the engine image. [Development and visual evaluation](docs/development.md) provides native PNG galleries, difficult fixtures and manual comparisons.

Performance measurements to date are local trials, not MacBook results or independent held-out quality evidence.

Dense or infeasible canvases can still produce tiny text, clipping, weak hierarchy or occlusion. Unsupported glyphs remain reported; recovery cannot supply missing characters. Opaque-subject localization is imperfect. Geometry/proxy checks do not certify readability, visual superiority or competition rank. The prior 87-case visual evaluation predates the latest performance/readability change.

## Submission

Stage one contains the engine, Dockerfile, README, schema, original assets/fonts, renderer and dependency/model manifests. Keep the repository **private**. Follow the [submission instructions](docs/submission.md#submit-and-freeze-the-evaluated-version) for the organizer’s form, access procedure and code freeze. That guide separates verified technical checks from unresolved model eligibility, registration and evaluator access. Code preparation does not submit the project or establish organizer approval.
