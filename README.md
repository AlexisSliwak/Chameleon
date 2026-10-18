# Chameleon

Retarget an existing design to a new canvas while preserving its elements, text, font families and image assets. The engine compares source-preserving fits, bounded responsive arrangements, editorial compositions and repeated-card layouts. It measures actual glyphs and visible image footprints, preserves backing relationships and reading order, and checks a shortlist against rendered imagery.

The engine, batch runner, tests, rendered comparison harnesses and local viewer are implemented. The current improvement round addresses tiny products, oversized action labels, detached contrast panels and reordered product cards. Selection remains deterministic and offline; it uses no hosted AI service or model weights.

There is one production engine and one selected output per task. Source-preserving fitting is an internal candidate and safety mechanism, not a separate product or runtime mode. Development scripts, tests, the viewer and saved experiments are excluded from the production image.

Verified final build: **71 tests passed**, 96 comparison outputs rendered, and all 34 full-engine source–target cases passed structural validation. The packaged offline runner produced all three supplied outputs with native dimensions and PNGs identical to the evaluation. All ten baked engine files and 41 locked dependencies matched their verification records. These checks establish execution and preservation, not a competition ranking.

Local evidence: [current public outputs](.project-evaluation/production-only-public/index.html), [current challenge outputs](.project-evaluation/production-only-challenges/index.html) and [production verification](.project-evaluation/production-v8/verification.json). The 96-render comparison above is preserved historical evidence; current evaluation commands produce only the selected engine output (14 public and 20 challenge cases). These ignored artifacts are absent from a fresh clone. Public and authored synthetic fixtures are development evidence, not an independent preference study. Dense banners still have small text, and the viewer's live Adobe Express sideload/import remains untested.

## Run the engine

Use Bash on Linux or WSL with a working Docker Linux-container engine. Run these commands from this repository's root—the directory containing this README and Dockerfile. In the parent research workspace, enter it with `cd implementation`. Do not clone or reset over the existing checkout.

```bash
docker version
docker build --platform linux/amd64 -t chameleon-engine .
mkdir -p output
docker run --rm --network none \
  --mount "type=bind,source=$(pwd -P)/input,target=/app/input,readonly" \
  --mount "type=bind,source=$(pwd -P)/output,target=/app/output" \
  chameleon-engine
```

The build fetches Python/renderer dependencies; execution has no network. No API key, hosted AI service or model weights are required. The Dockerfile pins its Python 3.11 base image by digest and bundles the supplied assets/fonts. `requirements.txt` includes `requirements.lock.txt`, which fixes 41 Python dependencies, including the renderer at commit `a17e1fb9a732959dd6c21ae168d5ee09d74bd64f`. System packages still resolve through the image's configured package repositories at build time. Host Python packages are not needed for this primary path.

Place task JSON files in `input/`. Each contains `source` (a canvas and elements) and `target_canvas` (width and height). The three supplied samples are included. For each successful task, `output/` receives `<task>_output.json` and `<task>_output.png`. The runner emits JSON-line diagnostics to stderr, continues after a failed task, and exits nonzero if any task fails or no tasks exist. Reusing the output directory replaces each task's prior output pair; use a new directory when preserving evidence.

The runner validates source/output contracts, rejects input mutation, and requires a real PNG. Renderer import failures propagate; there is no labeled-box fallback. The supplied advanced sample deliberately references missing `solstice_holiday_badge_2025.png` through element `holiday_watermark`; its official placeholder is expected. Do not add a replacement asset.

## Test and inspect rendered comparisons

The production image intentionally excludes development tests/scripts. Mount this checkout at `/app` to run the current source against the built runtime:

```bash
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine -m unittest discover -s tests
```

For a development comparison, choose a fresh run directory automatically:

```bash
chameleon_run=".project-evaluation/$(date -u +%Y%m%dT%H%M%SZ)-$$"
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine scripts/evaluate.py --output-dir "$chameleon_run"
```

Open the run's `index.html` to inspect the selected Chameleon output at each target size. The harness saves source previews, output JSON/PNGs, metrics, failures, environment details and a frozen manifest. It refuses an existing output directory. It tests the three public designs at deduplicated target sizes; these are development fixtures, not held-out evidence. Scores are engine proxies, not Adobe scores. Compare native-size PNGs: thumbnails can disguise tiny text.

The image runs baked engine code for the first command; the mounted test/evaluation commands run the current checkout. Rebuild after changes before claiming the production image is verified. Preserve the lockfile, base-image digest and resolved environment with comparisons; the production verification records the exact image and source hashes. Builds may differ as system packages resolve at build time.

The additional challenge harness evaluates the same production engine on five authored design families at 20 targets. Run it with the same mounted runtime and a fresh output directory:

```bash
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine scripts/evaluate_challenges.py \
  --output-dir ".project-evaluation/challenges-$(date -u +%Y%m%dT%H%M%SZ)-$$"
```

Use its `--baseline-dir` to compare the selected output against a previous production-engine run with identical fixture hashes. This is a regression check, not a second executable implementation. Saved reports retain the historical `full` result key for compatibility. Earlier baseline/ablation experiments remain archived outside the active workflow.

## Review the hardest cases

The [advanced review suite](tests/fixtures/hard-challenges/README.md) contains **28 cases across seven source families**: the unchanged official advanced sample and six authored stress designs. It covers 36-element catalogues, long styled copy and unbroken tokens, rotated groups, layered contrast, multiple disclaimers and extreme aspect ratios. These probe the published advanced requirements; they are not the organizer's hidden tests.

After building the image above, run from this repository root. This command tests the **baked production engine**, mounting only the review harness, fixtures and evidence directory:

```bash
mkdir -p .project-evaluation
chameleon_review=".project-evaluation/hard-review-$(date -u +%Y%m%dT%H%M%SZ)-$$"
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P)/scripts,target=/app/scripts,readonly" \
  --mount "type=bind,source=$(pwd -P)/tests/fixtures/hard-challenges,target=/app/tests/fixtures/hard-challenges,readonly" \
  --mount "type=bind,source=$(pwd -P)/.project-evaluation,target=/app/.project-evaluation" \
  chameleon-engine scripts/review_hard_cases.py --output-dir "$chameleon_review"
python3 -m http.server 5262 --bind 127.0.0.1 --directory "$chameleon_review"
```

Open `http://localhost:5262/` (stop the server with Ctrl-C). You can also open the generated `index.html` directly. Compare original and output, switch to **100%** to inspect actual size, filter warnings/failures and record a judgment for each case. Notes stay in that browser; **Export review notes** saves a portable JSON copy. Import accepts notes only for the exact same run. No notes are uploaded.

Each case invokes the real CLI in an isolated process and retains its input, output JSON/PNG, logs, timing and checks. The suite independently checks element/content preservation and PNG dimensions, freezes fixtures/harness and records engine/asset/font hashes. It retains failures in the gallery and returns nonzero for execution, preservation, source-render or integrity failure. The default 120-second per-case timeout is a local harness budget, not an official limit. Font-size and contrast warnings guide manual review; they do not fail the contract or certify visual quality. A fresh output directory is required.

Run the review-note logic tests with Node.js 18+:

```bash
node --test tests/review_notes.test.cjs
```

The Python suite above includes source validity, unchanged official-reference, preservation, timeout, failure-retention and gallery-escaping tests. Rebuild the image after engine changes before generating new production evidence.

The initial advanced run rendered all 28 cases with zero structural/execution failures and 22 visual-warning cases. The expanded Python suite passed 81 tests; the review-note and existing viewer JavaScript suites passed 16 tests. Browser checks verified filtering, native zoom, note persistence and export/import. Extreme outputs include 1–3px text and a typography case with ink/overflow warnings: these are exposed weaknesses, not visual passes. Local artifacts: [gallery](.project-evaluation/hard-review-v1/index.html) and [inspection notes](.project-evaluation/hard-review-v1/review-report.md).

## Review in the viewer

With Python 3.10+ on the local Linux host:

```bash
python3 viewer/serve.py
```

Open `http://localhost:5241/` and select original/output PNG and JSON files. The viewer compares fields and dimensions; it does not render JSON or certify pixel fidelity. [Viewer instructions](viewer/README.md) cover trusted local HTTPS, manifest-v2 sideloading, tests and the SDK action that imports one flattened PNG into Express. Local preview is separate from live Express validation and from the offline engine.

## How selection works—and its limits

- Source fitting preserves explicit groups and source anchors while fitting real text widths and font sizes.
- Contained text and visible image art can inherit an ungrouped rectangular backing as an internal layout unit. Original group IDs and stacking order remain unchanged.
- Responsive search combines sampled text/image/group states into rows, columns and split panels. Frontier pruning bounds work and can discard good layouts; it is not a global optimum or complete feasibility proof.
- Editorial candidates connect image, headline, supporting copy and action. Repeated-card candidates preserve equal treatment and source reading order. Both abstain on unsupported structures instead of silently squeezing content into spare slots.
- Composition ranking uses alpha-aware image prominence, source typography hierarchy, readable-copy floors, repeated-group flow and aspect-weighted source anchors. These are engineering preferences, not a learned aesthetic judge.
- Glyph bounds and missing-glyph checks follow the converter/renderer text path. Final imagery supplies contrast and busyness proxies for a small candidate shortlist.
- The validated source-fit incumbent always reaches pixel reranking. Contrast, tiny text and ink failures appear in quality warnings; warnings are not an official pass/fail threshold.
- Independent validation enforces conservation and the declared strict-bounds/style policy. Official requirements and conservative policy are distinct; the supplied [rules](RULES.md), [FAQ](FAQ.md) and [schema](chameleon_design_schema_v0.9.json) remain references, not an official scoring implementation.

Dense banners can still have tiny type, weak hierarchy, overlap or subject occlusion. A structurally valid result and a successful render do not establish legibility. The selected result includes no private diagnostics; inspect stderr/evaluation reports for quality warnings. No image regeneration, text rewriting, learned role classifier or visual-language model is implemented.

Keep the project repository private. Final hardware/model limits, exact deadline cutoff, intentional-bleed interpretation and the stage-one viewer requirement remain unresolved in the captured organizer material. This code has not been submitted or certified by Adobe.
