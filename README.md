# Chameleon

Retarget an existing design to a new canvas while preserving its elements, text, font families and image assets. The engine compares source-preserving fits, bounded responsive arrangements, editorial compositions and repeated-card layouts, then attempts measured ordered-flow repair when the selected layout has tiny text, overflow or collisions. It measures actual glyphs and visible image footprints, preserves backing relationships and checks proposals against rendered imagery.

The engine, batch runner, tests, rendered comparison harnesses and local viewer are implemented. Ordered-flow repair allocates space around shared text-size tiers and reflows supported multi-text panels before shrinking their content. Selection remains deterministic and offline; it uses no hosted AI service or model weights.

There is one production engine and one selected output per task. Source-preserving fitting is an internal candidate and safety mechanism, not a separate product or runtime mode. Development scripts, tests, the viewer and saved experiments are excluded from the production image.

Verified readability-refinement build: **109 engine tests passed**, plus **16 JavaScript and three viewer-server tests**. All **62 rendered development cases** passed preservation checks. Seven outputs enlarge 23 text blocks without shrinking any text or changing image fields; the other 55 JSON/PNG pairs are identical to the previous topology-search engine. These checks establish execution and local gains, not independent visual preference or competition rank.

Local evidence: [before/after comparison](.project-evaluation/text-refinement-research/final-index.html), [research and limitations](research/readability-refinement.txt), [per-block changes](.project-evaluation/text-refinement-research/final-text-changes.json), [hard-case gallery](.project-evaluation/text-final-hard/index.html), [public outputs](.project-evaluation/text-final-public/index.html), [challenge outputs](.project-evaluation/text-final-challenges/index.html) and [package verification](.project-evaluation/text-refinement-research/final-package-integrity.json). All three packaged offline output pairs match evaluation and twelve baked engine hashes match tested source. A two-case sample took 15.54 → 16.14 seconds and 268.2 → 274.8 MiB peak process RSS. The 62 cases include shared source families and repeated targets. Generated evidence is local and absent from a fresh clone; earlier experiments remain preserved. Extreme unbreakable text, tiny labels and some contrast failures remain. Live Adobe Express sideload/import is untested.

The latest build passed 117 Python tests (including five review-tool tests), 16 JavaScript tests and three viewer-server tests. All 62 rendered cases passed preservation with JSON/PNG pairs byte-identical to the preceding readability build. Three offline packaged pairs and all twelve baked engine hashes were verified. The latest contrast diagnostic detects mixed-background failures that average RGB can hide. A trial using it to select layouts was rejected after visual regressions; selected designs remain unchanged. See [contrast research and review gate](research/contrast-and-review.txt). The new sampled signal contributes to quality warnings, not an accessibility certificate.

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

## Anonymous manual comparison

Create a local review pack from two completed evaluation directories containing the same cases and source previews:

```bash
python3 scripts/blind_review.py create --before .project-evaluation/grid-v1-hard --after .project-evaluation/text-final-hard --output .project-evaluation/blind-review-new --seed 1031
```

These example runs exist only in the working workspace; use your own completed run paths on a fresh clone. Give reviewers only `blind-review-new/reviewer/`, which contains source previews, anonymous PNG pairs, `index.html` and `ratings.csv`. Keep the answer key private until ratings are complete. Each CSV dimension accepts A, B, tie or neither; severe failure accepts A, B, both or none. Leave unseen cases blank and retain every row.

```bash
python3 scripts/blind_review.py summarize --key .project-evaluation/blind-review-new/answer-key.json --ratings .project-evaluation/blind-review-new/reviewer/ratings.csv
```

The summary preserves unrated cases, severe failures and source-family grouping. It does not infer competition rank. The prepared [28-case review pack](.project-evaluation/contrast-distribution/blind-hard/reviewer/index.html) evaluates the preceding readability improvement; no human ratings have been entered.

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
- If the selected result has text below 12px, measured overflow or significant collision, ordered-flow repair samples shared typography tiers and solves contiguous row breaks using bounded frontiers and dynamic programming. Supported rectangular multi-text panels can compact their internal whitespace. Other compound and rotated groups retain their internal geometry. Unassociated decorative shapes cause this grammar to abstain. The already-rendered incumbent remains in competition; a repair must improve the same composition/raster score. Thresholds are local preferences, not official requirements.
- Flow repair protects each foreground image independently using an incumbent-relative optical short-side floor capped at 16px. Single unrotated image units pack around visible alpha support while retaining the unchanged full asset box and aspect ratio. Final footprint remeasurement, canvas validation and a guard against increased collision prevent small assets being sacrificed for an aggregate score. These local tolerances are engineering policy, not official thresholds or guarantees of recognizability.
- Weak repeated-card layouts additionally try measured row-major grids and image-beside/image-above arrangements. Shallow canvases can place headers, the existing action and footer in a side rail to recover card height. This bounded grammar preserves shared role tiers and source order, abstains above 12 cards, and tries at most 24 additional configurations. Unsupported structures retain the existing engine behavior. These candidates must satisfy the same image/collision guards and beat the retained raster-ranked result.
- When selected text remains below 12px, a bounded local refinement pass can grow standalone text while preserving its alignment anchor, and reflow existing rectangular text panels within available space. No member font may shrink; panel changes require actual font growth. Measured collision, clipping, missing glyphs and hierarchy inversion cannot increase, and the final rendered score must improve without worse low-contrast diagnostics. Images, rotations, group membership and literal styles remain fixed. The pass abstains above 24 eligible units; it does not prove optimality or fix an impossible unbreakable token.
- Independent validation enforces conservation and the declared strict-bounds/style policy. Official requirements and conservative policy are distinct; the supplied [rules](RULES.md), [FAQ](FAQ.md) and [schema](chameleon_design_schema_v0.9.json) remain references, not an official scoring implementation.

Dense banners can still have tiny type, weak hierarchy, overlap or subject occlusion. Ordered-flow repair samples a finite set of widths and text tiers, caps row frontiers and abstains above 64 layout units; it cannot prove global infeasibility. Very long unbreakable tokens may not fit a narrow canvas even at tiny type under the unchanged converter and content rules. A structurally valid result and a successful render do not establish legibility. The selected result includes no private diagnostics; inspect stderr/evaluation reports for quality warnings. No image regeneration, text rewriting, learned role classifier or visual-language model is implemented.

Keep the project repository private. Final hardware/model limits, exact deadline cutoff, intentional-bleed interpretation and the stage-one viewer requirement remain unresolved in the captured organizer material. This code has not been submitted or certified by Adobe.
