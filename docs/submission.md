# Submission readiness

This document distinguishes the prepared source package from organizer approval. The root README is the evaluator entry point. Stage one is engine-only; Express add-on work is reserved for the finale. No form has been submitted and no evaluator invitation has been sent by this audit.

## Deliverable inventory

| Item | Location / status |
| --- | --- |
| Autonomous engine and batch entry point | engine/resize.py and engine/main.py |
| Offline linux/amd64 build | Dockerfile, requirements.txt, requirements.lock.txt |
| Original inputs, assets, fonts and schema | input/, brand_kit/, chameleon_design_schema_v0.9.json |
| Official conversion path | renderer/; pinned cr-renderer dependency |
| Model identity, hashes and notices | deployment/; included even when inference is off |
| Setup, approach, dependencies and limitations | README.md |
| Local visual review, reproduction and difficult fixtures | tests/, scripts/, docs/development.md |

The organizer recap dated October 23 explicitly requests setup, model information, dependencies and operating limitations. The captured main brief (sections 7.1–7.3) specifies code, Dockerfile and a short README, with offline execution and build-time dependencies. The current stage-one scope is the engine, consistent with the main brief; Express add-on work is for the finale. The older FAQ wording is preserved as source history, not used to add an Express gate to this submission. RULES.md and FAQ.md remain unchanged organizer references. Raw correspondence stays outside this repository.

## Verification for this preparation

Audit baseline before history cleanup: ad1ebfa. Historical evidence retains its original commit IDs; the local history-cleanup report records their replacements. Three independent audit assignments inspected engine/contract flows, packaging and evidence. No concrete production behavior defect was established. Corrected the stale no-model claim, clarified mixed stderr, and separated evaluator setup from development history.

After removing the Express add-on, verification in .project-audit/remove-express-20261030T205102Z/ passed all 187 Python tests and all three review-note JavaScript tests. A clean tracked-file build (cache-assisted, linux/amd64) passed both network-disabled public batches. All six JSON/PNG pairs match the preceding release byte for byte; all 14 baked engine hashes match source. The engine, renderer, assets, fonts, fixtures and evaluation tools are unchanged. Maintained documentation links and Bash examples passed checks. Historical logs retain their original commit IDs and test counts.

Repository visibility was verified PRIVATE during preparation. Dependencies were not downloaded again without cache; actual Mac performance remains unverified. No Express integration is required for this engine-only preparation.

## Current clearance status

Follow-up evidence is saved locally in .project-audit/clearance-20261030/. The latest organizer email reiterates individual/team registration, same eligible university and U.S. Adobe Creative Campus eligibility for finalists. No new model approval or evaluator accounts were supplied in that email. Current repository access contains the owner and existing teammate, not a verified evaluator.

The portal/deadline check is complete. Registration, model eligibility and evaluator access remain separate logistics/rules questions. Actual Mac testing is an outstanding engineering validation, not an invented organizer prerequisite to sending a submission. The user has instructed that no email or submission be sent yet.

## External checks before sending

- The live form and October 30 deadline email were checked: **October 30, 2026, 11:59 PM Pacific Time**. The form writes PST, while the current email repeatedly says Pacific Time/PT; use the Pacific deadline rather than assuming an extra hour. The latest short link resolves to the archived form. Team name is required; team-size choices are two or three. Later pages require the registered team name before review. No submission has been made.
- Grant the designated evaluators access to the private repository using the organizer’s instructions. Do not infer a reviewer account or make the repository public.
- Confirm model approval and the size cap. The default off mode avoids inference but the image still contains the model/runtime. If packaged-model eligibility is refused, a packaging change and fresh verification are needed before submission.
- Verify the final machine limits and run the image on the actual Mac/reference environment. Local WSL/Docker results do not establish Apple Silicon latency or peak memory.
- Confirm registration and any applicable prize/travel eligibility separately from code correctness.

No hard stage-one execution-time cutoff is stated in the captured rules. This does not imply unlimited memory or hardware resources. No official quality score, independent held-out aesthetic win or competition rank has been established.

## Clean source package

Use the committed repository revision as the source of truth. A Git source archive includes the engine code, documentation and original brand kit; the Express add-on is removed from the repository and its published branch history. It excludes Git history, local credentials, environments, generated evaluation/audit runs and the outer correspondence workspace. Weights are retrieved and verified during Docker build, not stored in the source archive. This remains a private project package.

The archive is a prepared deliverable, not an uploaded submission. The organizer’s actual access/upload instructions take precedence over any local packaging convention.
