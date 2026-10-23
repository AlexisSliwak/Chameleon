# Submission readiness

This document distinguishes the prepared source package from organizer approval. The root README is the evaluator entry point. No form has been submitted and no evaluator invitation has been sent by this audit.

## Deliverable inventory

| Item | Location / status |
| --- | --- |
| Autonomous engine and batch entry point | engine/resize.py and engine/main.py |
| Offline linux/amd64 build | Dockerfile, requirements.txt, requirements.lock.txt |
| Original inputs, assets, fonts and schema | input/, brand_kit/, chameleon_design_schema_v0.9.json |
| Official conversion path | renderer/; pinned cr-renderer dependency |
| Model identity, hashes and notices | deployment/; included even when inference is off |
| Setup, approach, dependencies and limitations | README.md |
| Viewer add-on | viewer/; official manifest and standalone-browser checks pass; live Express outstanding |
| Reproduction and difficult fixtures | tests/, scripts/, docs/development.md |

The organizer recap dated October 23 explicitly requests setup, model information, dependencies and operating limitations. The captured main brief (sections 7.1–7.3) specifies code, Dockerfile and a short README, with offline execution and build-time dependencies. The supplied FAQ additionally lists a required unscored viewer; that conflict remains unresolved. RULES.md and FAQ.md are preserved organizer references, not rewritten as our interpretation. Raw correspondence stays outside this repository.

## Verification for this preparation

Audit baseline: ad1ebfa. Three independent audit assignments inspected engine/contract flows, packaging and evidence. No concrete production behavior defect was established. Corrected the stale no-model claim, clarified mixed stderr, and separated evaluator setup from development history.

Final checks are recorded locally in .project-audit/20261030T191619Z-6259bcf1/. Generated audit reports and test logs are not in the submission archive. Verification completed: 187 Python tests in one full discovery run, 16 JavaScript tests, three viewer-server tests and viewer syntax checks passed. All 14 Bash blocks passed syntax checks and all local documentation links resolved in the working workspace; optional generated-evidence links are labeled absent from a fresh clone. A tracked-file-only, cache-assisted linux/amd64 build passed both network-disabled public batches (off and regions). All six JSON/PNG pairs match the preceding release byte for byte; all 14 baked engine hashes match source. Repository visibility was verified PRIVATE. Dependencies were not downloaded again without cache; actual Mac/Express environments remain unverified.

## Current clearance status

Follow-up evidence is saved locally in .project-audit/clearance-20261030/. Adobe manifest package 3.11.0 passed both validation modes and rejected a missing-entrypoint negative control. The standalone viewer loaded real warmup source/output files and displayed preserved fields. The latest organizer email reiterates individual/team registration, same eligible university and U.S. Adobe Creative Campus eligibility for finalists. No new model approval or evaluator accounts were supplied in that email. Current repository access contains the owner and existing teammate, not a verified evaluator.

These checks close portal/deadline, manifest-schema and basic browser-preview gaps. They do not clear registration, model eligibility, evaluator access or live Express import. Actual Mac testing is an outstanding engineering validation, not an invented organizer prerequisite to sending a submission. An unsent organizer clarification has been prepared; sending it requires explicit user authorization.

## External checks before sending

- The live form and October 30 deadline email were checked: **October 30, 2026, 11:59 PM Pacific Time**. The form writes PST, while the current email repeatedly says Pacific Time/PT; use the Pacific deadline rather than assuming an extra hour. The latest short link resolves to the archived form. Team name is required; team-size choices are two or three. Later pages require the registered team name before review. No submission has been made.
- Grant the designated evaluators access to the private repository using the organizer’s instructions. Do not infer a reviewer account or make the repository public.
- Confirm model approval and the size cap. The default off mode avoids inference but the image still contains the model/runtime. If packaged-model eligibility is refused, a packaging change and fresh verification are needed before submission.
- Verify the final machine limits and run the image on the actual Mac/reference environment. Local WSL/Docker results do not establish Apple Silicon latency or peak memory.
- Resolve the stage-one viewer requirement and complete authenticated Express sideload/import if required. Official Adobe manifest validation now passes; standalone browser loading/comparison and Fit/Actual size also pass. Express currently requires user sign-in and trusted local HTTPS.
- Confirm registration and any applicable prize/travel eligibility separately from code correctness.

No hard stage-one execution-time cutoff is stated in the captured rules. This does not imply unlimited memory or hardware resources. No official quality score, independent held-out aesthetic win or competition rank has been established.

## Clean source package

Use the committed repository revision as the source of truth. A Git source archive includes the tracked code, documentation, original brand kit and viewer; it excludes Git history, local credentials, environments, generated evaluation/audit runs and the outer correspondence workspace. Weights are retrieved and verified during Docker build, not stored in the source archive. This remains a private project package.

The archive is a prepared deliverable, not an uploaded submission. The organizer’s actual access/upload instructions take precedence over any local packaging convention.
