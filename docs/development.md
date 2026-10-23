# Development and visual evaluation

Run commands from the repository root after the [README](../README.md) build. Saved galleries are local evidence, absent from a fresh clone; the commands generate new runs. Historical counts below describe their dated experiments, not the current release test count.

## Test and inspect rendered comparisons

The production image intentionally excludes development tests/scripts. Mount this checkout at `/app` to run the current source against the built runtime:

```bash
docker run --rm --network none -e CHAMELEON_ADVISOR=off --entrypoint python \
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

The production command in the root README runs baked engine code; the mounted test/evaluation commands below run the current checkout. Rebuild after changes before claiming the production image is verified. Preserve the lockfile, base-image digest and resolved environment with comparisons; the production verification records the exact image and source hashes. Builds may differ as system packages resolve at build time.

The additional challenge harness evaluates the same production engine on five authored design families at 20 targets. Run it with the same mounted runtime and a fresh output directory:

```bash
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine scripts/evaluate_challenges.py \
  --output-dir ".project-evaluation/challenges-$(date -u +%Y%m%dT%H%M%SZ)-$$"
```

Use its `--baseline-dir` to compare the selected output against a previous production-engine run with identical fixture hashes. This is a regression check, not a second executable implementation. Saved reports retain the historical `full` result key for compatibility. Earlier baseline/ablation experiments remain archived outside the active workflow.

## Review the hardest cases

The [advanced review suite](../tests/fixtures/hard-challenges/README.md) contains **28 cases across seven source families**: the unchanged official advanced sample and six authored stress designs. It covers 36-element catalogues, long styled copy and unbroken tokens, rotated groups, layered contrast, multiple disclaimers and extreme aspect ratios. These probe the published advanced requirements; they are not the organizer's hidden tests.

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

The initial advanced run rendered all 28 cases with zero structural/execution failures and 22 visual-warning cases. The expanded Python suite passed 81 tests; the review-note and existing viewer JavaScript suites passed 16 tests. Browser checks verified filtering, native zoom, note persistence and export/import. Extreme outputs include 1–3px text and a typography case with ink/overflow warnings: these are exposed weaknesses, not visual passes. Local artifacts: [gallery](../.project-evaluation/hard-review-v1/index.html) and [inspection notes](../.project-evaluation/hard-review-v1/review-report.md).

## Extreme-case review

The additional suite deliberately includes infeasible targets and source defects. Expect visual-review flags for tiny copy, missing glyphs, overflow and contrast. Inspect actual PNGs; preservation passes alone are insufficient.

```bash
docker run --rm --network none --entrypoint python -v "$PWD:/app" chameleon-engine scripts/review_hard_cases.py --suite-dir tests/fixtures/extreme-challenges --output-dir .project-evaluation/extreme-review-new
```

The output directory must not already exist. The gallery retains every case, source preview, real PNG, JSON, failure and diagnostic. The [split-layout investigation](../research/split-layout-study.txt) records rejected split/spacing alternatives; [open its side-by-side comparisons](../.project-evaluation/split-layout/index.html) or the [refreshed source/output review](../.project-evaluation/split-layout/review/index.html). Its 120-second per-case harness timeout is a local test budget, not an official hackathon limit.

## Anonymous manual comparison

Create a local review pack from two completed evaluation directories containing the same cases and source previews:

```bash
python3 scripts/blind_review.py create --before .project-evaluation/grid-v1-hard --after .project-evaluation/text-final-hard --output .project-evaluation/blind-review-new --seed 1031
```

These example runs exist only in the working workspace; use your own completed run paths on a fresh clone. Give reviewers only `blind-review-new/reviewer/`, which contains source previews, anonymous PNG pairs, `index.html` and `ratings.csv`. Keep the answer key private until ratings are complete. Each CSV dimension accepts A, B, tie or neither; severe failure accepts A, B, both or none. Leave unseen cases blank and retain every row.

```bash
python3 scripts/blind_review.py summarize --key .project-evaluation/blind-review-new/answer-key.json --ratings .project-evaluation/blind-review-new/reviewer/ratings.csv
```

The summary preserves unrated cases, severe failures and source-family grouping. It does not infer competition rank. The prepared [28-case review pack](../.project-evaluation/contrast-distribution/blind-hard/reviewer/index.html) evaluates the preceding readability improvement; no human ratings have been entered.

## Inspect deeper visual evidence

The offline perceptual-review tool adds per-element occlusion and glyph-local contrast evidence to the existing composition metrics. It renders each text/image with and without later layers, and uses diagnostic text-color probes to locate actual glyph coverage. It never modifies submitted designs or changes production selection. Human review covers readability, hierarchy, branding, grouping, spacing, balance, layering and polish; no human ratings are filled automatically.

Run from this checkout with the built Docker runtime and an existing task/output pair. Use a fresh report directory:

```bash
docker run --rm --network none --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=/app" \
  chameleon-engine -m scripts.perceptual_review \
  --task input/chameleon_sample_level1_warmup.json \
  --output output/chameleon_sample_level1_warmup_output.json \
  --report-dir .project-evaluation/perceptual-review-new
```

Open the report directory's `index.html` file for source/output previews, per-element findings and contribution images. `report.json` contains composition metrics, input/runtime hashes, render count, elapsed time and coverage; `human-review.json` is an unfilled structured human-review record. The tool refuses to overwrite an existing directory, rejects contract-invalid outputs and retains processing failures in `failure.json`. Run the engine first if the output JSON does not yet exist.

By default it reviews up to 64 nonempty text/image elements per design at a maximum raster dimension of 1024px. `--max-elements` (1–256) and `--max-size` (64–2048) adjust these explicit budgets; omitted IDs and text without reliable glyph coverage remain unassessed. This can require hundreds of diagnostic renders for a dense source/output pair. It is a development tool excluded from the production image, so mount the checkout as above. Contribution loss cannot identify a covered face or logo, and glyph contrast is not WCAG certification. Inspect original PNGs at native size and use the anonymous A/B workflow for independent preference comparisons. See [evaluation evidence and limitations](../research/perceptual-evaluation.txt).

## Review in the viewer

With Python 3.10+ on the local Linux host:

```bash
python3 viewer/serve.py
```

Open `http://localhost:5241/` and select original/output PNG and JSON files. The viewer compares fields and dimensions; it does not render JSON or certify pixel fidelity. [Viewer instructions](../viewer/README.md) cover trusted local HTTPS, manifest-v2 sideloading, tests and the SDK action that imports one flattened PNG into Express. Local preview is separate from live Express validation and from the offline engine.

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
- When selected text remains below 12px, a bounded local refinement pass can grow standalone text while preserving its horizontal alignment anchor and either its top or bottom edge, and reflow existing rectangular text panels within available space. No member font may shrink; panel changes require actual font growth. Measured collision, clipping, missing glyphs and hierarchy inversion cannot increase, and the final rendered score must improve without worse low-contrast diagnostics. Images, rotations, group membership and literal styles remain fixed. The pass abstains above 24 eligible units; it does not prove optimality or fix an impossible unbreakable token.
- After selection, missing-glyph recovery may enlarge up to 24 unrotated affected text blocks within their existing boxes. It preserves other elements, rejects worsened safety/hierarchy diagnostics, and keeps missing-glyph warnings. It cannot supply unsupported characters or solve an impossible token.
- Independent validation enforces conservation and the declared strict-bounds/style policy. Official requirements and conservative policy are distinct; the supplied [rules](../RULES.md), [FAQ](../FAQ.md) and [schema](../chameleon_design_schema_v0.9.json) remain references, not an official scoring implementation.

Dense banners can still have tiny type, weak hierarchy, overlap or subject occlusion. Ordered-flow repair samples a finite set of widths and text tiers, caps row frontiers and abstains above 64 layout units; it cannot prove global infeasibility. Very long unbreakable tokens may not fit a narrow canvas even at tiny type under the unchanged converter and content rules. A structurally valid result and a successful render do not establish legibility. The selected result includes no private diagnostics; inspect stderr/evaluation reports for quality warnings. No image regeneration or text rewriting is implemented. Optional local vision-language inference proposes asset regions; deterministic checks control acceptance.

Keep the project repository private. Final hardware/model limits, exact deadline cutoff, intentional-bleed interpretation and the stage-one viewer requirement remain unresolved in the captured organizer material. This code has not been submitted or certified by Adobe.
