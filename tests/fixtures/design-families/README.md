# Synthetic design challenges

Five agent-authored development designs expand the public samples' composition coverage. They reuse only supplied fonts and assets, with original text and ordinary schema shapes. **These are synthetic challenges, not independent human-quality holdouts.** They were authored after inspecting the public sample outputs and are suitable for finding regressions, not claiming generalization or aesthetic superiority.

The five named design JSON files use the normal task envelope (`source`, `target_canvas`). Each has one default target. `challenge-matrix.json` lists four targets per family, including an identity case; it is metadata, not an engine task. Do not mount this whole directory as batch input: copy only the five design task files into an isolated input directory, or have a harness materialize matrix targets into unique tasks. Preserve originals and run outputs separately. Nothing here runs automatically as part of test discovery.

| Family | Source → default target | Source intent and useful failure checks |
| --- | --- | --- |
| editorial-event | 900×1200 → 1200×628 | Strong left title, paired time/location, dark program panel and separate CTA. Check panel/text association, reading order and title prominence. |
| asymmetric-space | 1200×800 → 600×900 | Large left headline and small bottom-right product with intentional empty space. Check whether packing erases asymmetry or wrongly enlarges a supporting image. |
| commerce-triptych | 1200×900 → 600×1200 | Three equal explicit card groups, each with product/name/description/price. Check equal treatment, internal geometry, order and readable prices under stacking. |
| transparent-hero | 1200×900 → 900×1200 | Light halo behind a transparent bottle, opposite a copy/CTA panel. Check intentional overlap, product prominence and whether the halo follows the product without an explicit group. |
| rotated-workshop | 1000×1000 → 1400×600 | Tilted ticket with grouped text beside editorial copy. Check rotated bounds, group-relative transforms, internal containment and hierarchy. |

The matrix includes extreme banners as stress tests; preserving every word may make readable output infeasible. Retain failures and disclose minimum font sizes rather than awarding success for structural validity alone. The event and hero supporting panels are deliberately not explicitly grouped with their text/image: these probe association inference. The commerce cards and rotated ticket test explicit groups.

## Validation status

Task structure, unique IDs, positive dimensions, source box bounds, supplied asset paths, font-family names and matrix references passed static checks. All five sources then rendered with the official renderer and were visually inspected. Commerce prices exposed an authoring defect (truncated currency strings); they were corrected to USD 18, USD 24 and USD 28, and the corrected source was inspected. The original run is preserved at `.project-evaluation/challenges-v3/` with a supersession note. The corrected baked-v3 baseline at `.project-evaluation/challenges-v3-corrected/` completed with five source previews and 40 successful target renders; both methods passed structural validation on all 20 pairs. This does not establish visual quality: inspected outputs detach the editorial panel from its white text and the transparent hero from its halo. These checks are not human preference validation.

## Evaluation harness

The latest baked-engine run at `.project-evaluation/challenges-v8/` completed all 40 target renders and five source previews. Its ten engine-file hashes matched final source. All 40 PNGs, 40 output JSON files and five previews match v6 byte for byte, restoring the transparent-hero portrait that regressed in the preserved v7 experiment. The v8 `report.md` carries forward the eight editorial/commerce comparisons against corrected-v3: six agent-judged wins and two ties. This is scoped development inspection, not independent human validation; the extreme editorial banner remains unreadable and some metadata/action placement is weak. Earlier runs and their reports remain preserved.

From the implementation repository, use the Docker runtime and run `scripts/evaluate_challenges.py --output-dir <fresh-directory>`. It tests source fit and the full engine on all 20 matrix cases, saves source previews and incremental per-case JSON/PNG/results, and builds an HTML gallery. Manifest, evaluator copy, frozen inputs, engine/asset/font hashes and environment identify the run. Existing output directories are rejected. Source-render or case failures produce a nonzero exit.

For a later run, add `--baseline-dir <prior-run>` to include prior/current full-engine PNGs side by side. Fixture and matrix hashes must match. All comparison directories must be visible inside the container under paths that retain their relative relationship on the host. Mount only this script, fixtures and output parent to evaluate a baked baseline engine; bind-mount the entire checkout only when intentionally evaluating current source. Do not confuse the two.

Test identity outputs as well as the other matrix targets. Record engine revision, actual renderer/fonts, elapsed time, failures and source/output PNGs.

Judge source intent alongside native-size pixels: headline/body hierarchy, coherent clusters, product prominence, useful whitespace, group transforms and reading order. Compare source fit and full engine; do not treat the author's intended composition as a single mandatory target arrangement. Any fixes driven by these fixtures make them development data thereafter.

Current evaluation produces one selected Chameleon result per target: 20 target renders plus five source previews. Earlier 40-render reports above included a standalone source-fit comparison and are preserved historical evidence. The optional prior-run comparison reads saved selected outputs; it does not run another engine version.
