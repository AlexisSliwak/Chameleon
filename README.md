# Chameleon

An offline design-retargeting engine for the Adobe University Hackathon. Given a source design and target canvas, it produces one adapted design JSON and a PNG through the supplied official renderer. It preserves every element ID, literal text, font family and image asset, and selects the result automatically.

## Build and run

Use Bash on Linux, macOS or WSL with a running Docker Linux-container engine. Run from this repository’s root (the directory containing this README and Dockerfile). The build needs internet access; execution does not. No host Python packages, API keys, GPU or external model service are required.

```bash
docker version
docker build --platform linux/amd64 -t chameleon-engine .
mkdir -p output
docker run --rm --platform linux/amd64 --network none \
  --mount "type=bind,source=$(pwd -P)/input,target=/app/input,readonly" \
  --mount "type=bind,source=$(pwd -P)/output,target=/app/output" \
  chameleon-engine 2>output/run.log
```

On Apple Silicon, Docker must support linux/amd64 emulation. The container uses CPU execution; host Metal acceleration is not assumed. Native MacBook/reference-machine performance has not been measured. The captured rules name Apple M5 Pro but leave exact CPU/RAM/disk limits unresolved.

The included three sample tasks should produce three JSON/PNG pairs and exit with status 0. Inspect the PNGs at their native size. The advanced sample deliberately references missing `solstice_holiday_badge_2025.png`; the renderer’s placeholder is expected. Do not add a replacement asset.

### Benchmark your inputs

Put task JSON files in `input/`, or replace the input mount with an absolute directory containing the organizers’ tasks. Each task has `source: {canvas, elements}` and `target_canvas: {width, height}`; see the [schema](chameleon_design_schema_v0.9.json) and [sample](input/chameleon_sample_level1_warmup.json). Keep input and output directories separate.

For each successful `<task>.json`, the runner writes `<task>_output.json` and `<task>_output.png`. Output JSON contains only the adapted design. Task failures remove that task’s stale output pair, record the error and allow later tasks to run. Any task failure or an empty input directory produces a nonzero exit status. Reusing an output directory replaces matching output pairs.

`run.log` contains one runner JSON record per task, including timings, warnings and layout diagnostics. Native dependencies may also write plain-text warnings to stderr, so the whole log is not a strict JSONL file. A valid design and real PNG are required; there is no fallback that replaces the design with labeled boxes.

## Approach

1. Measure actual font glyphs, image alpha support, explicit groups and inferred backing relationships.
2. Generate source-preserving fits, bounded responsive row/column/split layouts, editorial arrangements and repeated-card layouts. Sampled frontiers balance footprint and utility; they are not an exhaustive optimizer.
3. Rank valid candidates using source-relative composition and typography, then inspect rendered contrast and busyness for a small shortlist.
4. Attempt bounded flow, grid and text refinements for weak layouts. A wider retry for tiny text preserves each incumbent font-size floor and source hierarchy. Retain the incumbent unless the candidate passes the relevant guards and improves the selection score.
5. Validate conservation, target canvas, styles and rotated bounds independently; render the selected design with the pinned official converter/renderer.

There is one production engine and one selected result per task. Source fitting is an internal candidate. Scores, font thresholds and search budgets are engineering choices, not Adobe’s scoring formula. The engine never rewrites copy or regenerates asset pixels. It conservatively preserves styles, group IDs and stacking, and enforces strict canvas bounds; these policies are stricter than some unresolved rule interpretations.

## Dependencies and optional model

The Dockerfile pins Python 3.11 by image digest. [requirements.lock.txt](requirements.lock.txt) pins 41 Python dependencies, including `cr-renderer` at `a17e1fb9a732959dd6c21ae168d5ee09d74bd64f`. Supplied fonts/assets and the unchanged converter are included. System packages resolve at build time; a cache-assisted build is not a guarantee of future byte-identical images.

The image also includes CPU `llama.cpp` at `889f2ec96deacbc2d8a9a67dbe181eaa43a2fb3b` and unmodified public **Qwen3.5-2B Q4_K_M**, with an F16 vision projector. [deployment/model.json](deployment/model.json) records immutable download URLs, revisions, file sizes and verified SHA-256 hashes. The two weight files total **1,949,063,104 bytes**; allow additional disk space for the runtime, image and build layers. See the [licenses and notices](deployment/NOTICES.txt). No fine-tuned adapter is used.

| Setting | Behavior |
| --- | --- |
| `CHAMELEON_ADVISOR=off` (default) | Deterministic layout search; no model inference. |
| `CHAMELEON_ADVISOR=regions` | Exact alpha-region guidance for transparent assets and bounded local vision-language inference for other assets; renderer-measured visibility and safety checks control acceptance. |

To enable guidance, add `-e CHAMELEON_ADVISOR=regions` before `chameleon-engine` in the run command. Identity cases can bypass guidance; failures/timeouts retain the deterministic result with a diagnostic. Model requests use only loopback inside the network-isolated container. No critic model or hosted API is used.

**Disabling inference does not remove the weights or runtime from the image, or skip their build-time download.** The approved-model list and size cap were not supplied in the captured organizer material. Public availability and licensing do not prove eligibility. The default remains off while eligibility and independent visual benefit are unresolved. [Region-guidance details](docs/region-guidance.md) cover limits, caching, fallback behavior and reproducible controls.

Our resource trial used `--cpus 8 --memory 8g`; these are local measurement settings, not organizer requirements. The captured [submission rules](RULES.md) specify no hard stage-one execution-time cutoff, but speed, reliability and the actual reference machine still matter.

## Verification and limitations

The submission audit passed all 187 Python tests in one complete run, 16 JavaScript tests and three viewer-server tests in the wider development repository. A tracked-file build (cache-assisted) passed offline public runs with guidance off and on; all six JSON/PNG pairs match the prior release, and all 14 baked engine files match current source. See [submission readiness](docs/submission.md) for the final verification record and remaining external checks.

To test current source against the built runtime:

```bash
docker run --rm --platform linux/amd64 --network none \
  -e CHAMELEON_ADVISOR=off --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine -m unittest discover -s tests
```

This mount tests the checkout; the build/run command above tests baked production code. Development tests, scripts and the viewer are excluded from the engine image. [Development and visual evaluation](docs/development.md) provides native PNG galleries, difficult fixtures and manual comparisons.

The latest [performance study](research/performance-review.txt) measured 29% less summed resize time with guidance off and 24% less with regions on across eight development cases run twice. Seven cases retained identical outputs. One difficult banner improved body text from 8 to 14px and its action label from 5 to 8px, at greater latency for that case. These are host measurements, not MacBook results or independent held-out quality evidence.

Dense or infeasible canvases can still produce tiny text, clipping, weak hierarchy or occlusion. Unsupported glyphs remain reported; recovery cannot supply missing characters. Opaque-subject localization is imperfect. Geometry/proxy checks do not certify readability, visual superiority or competition rank. The prior 87-case visual evaluation predates the latest performance/readability change.

## Submission contents

Submit this private repository’s code, Dockerfile and README using the organizer’s submission channel. Stage one contains the engine, schema, original assets/fonts, renderer, dependency/model manifests, tests and run instructions. Do not submit the outer personal research/correspondence workspace, local virtual environments or generated audit/evaluation directories. Keep evaluator access explicit; do not make the repository public.

Stage one is the engine submission. Adobe Express add-on development belongs to the finale and is not a stage-one setup or acceptance step. Existing viewer source is retained separately in the repository for possible future work and excluded from Git source archives and the production image.

The current organizer email sets the deadline at **October 30, 2026, 11:59 PM Pacific Time**. The live form is reachable. Before sending, resolve the remaining checks in [submission readiness](docs/submission.md): final team/registration details, private evaluator access and model eligibility. Code preparation does not submit the project or establish organizer approval.
