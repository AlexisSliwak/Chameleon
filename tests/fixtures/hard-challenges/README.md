# Advanced review fixtures

Seven source families, four targets each, exercised through the single production CLI. Follow the [repository instructions](../../../README.md#review-the-hardest-cases) to generate the offline review gallery.

The official level-three reference is a byte-identical copy of the supplied advanced input. Its missing holiday badge is intentional. The other six sources are authored development fixtures using only the supplied assets and fonts. They are valid, readable source compositions; target pressure should expose retargeting weaknesses rather than malformed input. Unit tests check source geometry, measured text fit and missing glyphs before execution.

| Family | Elements | Target dimensions | Main pressure |
| --- | ---: | --- | --- |
| Official advanced | 17 | 728×90, 1080×1350, 300×250, 113×997 | Official reference, long copy, expected missing asset |
| Dense launch | 24 | 1600×1800, 600×900, 160×600, 728×90 | Six badges, rotated label, three disclaimers |
| Six-product catalogue | 36 | 1800×1600, 600×1200, 1600×400, 728×90 | Repeated groups, ordering, equal product treatment |
| Typography pressure | 16 | 1400×1700, 600×900, 320×100, 113×997 | Styled runs, line breaks, long URL/token, accented text |
| Rotated programme | 22 | 1600×1500, 600×900, 1600×400, 160×600 | Rotated images/groups, dense schedule, two actions |
| Layered contrast | 14 | 1600×1200, 900×1200, 300×250, 728×90 | Translucent panels, image occlusion, two brand anchors |
| Independent disclaimers | 19 | 1600×1800, 600×900, 970×90, 113×997 | Separate legal copy, empty group ID, differing image boxes |

The published advanced challenge allows arbitrary element counts, awkward content and extreme target ratios. This suite exercises those dimensions without claiming equivalence to unknown hidden inputs or guaranteeing that every dense design can remain readable in a tiny canvas. Identity-size controls help distinguish source defects from resizing defects. Targets from the same family are correlated, not independent trials.

The machine-readable specification is [suite.json](suite.json): provenance, pressure labels, expected missing assets, target dimensions and case-specific review prompts. Do not change old run directories when updating fixtures. Freeze a new run and compare matching fixture/engine hashes. Keep failures, including unattractive but structurally valid outputs.

Manual review should assess all literal text at native size, image recognition, overlap, contrast, source hierarchy, reading order, group/backdrop relationships and action visibility. The gallery's 8px/12px font alerts and contrast/collision proxies are local engineering preferences, not official scoring thresholds. A zero exit code means execution and preservation checks passed; every output still needs a visual judgment.

The harness never modifies the engine or supplies fixture-specific exceptions. Generated evidence is ignored by Git. Export browser review notes to retain human judgments alongside the immutable run data.
