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

The final readiness audit tested a clean Git export of 1b7ac95. Subsequent audit changes affect submission documentation only. Three independent reviews covered the engine contract, packaging and organizer instructions; a cross-review challenged the findings. Two documentation inconsistencies were corrected. No new production defect was established in the inspected paths.

Local evidence is retained in .project-audit/20261030T212753Z-61b02632/ and excluded from the submission package:

- All 187 Python tests and three review-note JavaScript tests passed from the exported source.
- A cache-assisted linux/amd64 build passed network-disabled public batches with guidance off and on. All six JSON/PNG pairs match the preceding verified release.
- Additional baked-runner checks rejected invalid and empty inputs, removed stale failed outputs and completed the next valid task with unchanged JSON/PNG results.
- Maintained documentation links and Bash examples passed checks. Original organizer captures, renderer, engine, assets, fonts and evaluation tools remain unchanged.
- Both pinned model download URLs responded successfully with the expected file lengths. This verifies availability, not a complete cold download or model eligibility.
- GitHub visibility was checked as private, with the owner and existing teammate as collaborators. No evaluator identity or access procedure was supplied in the captured sources.

Dependencies were not downloaded again without cache. Actual Mac/reference-machine performance, hidden-test quality and organizer model eligibility remain unverified. Express integration is outside stage-one scope. Historical audit logs retain their original commit IDs and test counts.

## Current clearance status

Follow-up evidence is saved locally in .project-audit/clearance-20261030/. The latest organizer email reiterates individual/team registration, same eligible university and U.S. Adobe Creative Campus eligibility for finalists. No new model approval or evaluator accounts were supplied in that email. Current repository access contains the owner and existing teammate, not a verified evaluator.

The portal/deadline check is complete. Registration, model eligibility and evaluator access remain separate logistics/rules questions. Actual Mac testing is an outstanding engineering validation, not an invented organizer prerequisite to sending a submission. The user has instructed that no email or submission be sent yet.

## Submit and freeze the evaluated version

One team member submits for the whole team through the [official form](https://forms.cloud.microsoft/r/i4KNM7VmxS). The organizer email requests the registered team name, each teammate's name and registered email, university, major, GitHub repository URL and January 11–13, 2027 finale availability. It explicitly says no separate file upload is needed. These later fields are described by the email; only the initial form page and team-name validation were inspected directly. Follow any additional instructions shown in the form.

1. Finish the intended changes, push the final revision and record its full commit ID. Confirm that the repository contains the engine, Dockerfile, README, dependencies and original assets/fonts needed by the documented build.
2. Keep the repository private. Enter its URL in the form. Providing the URL does not grant access: follow any evaluator-access instructions supplied by Adobe or the form. The captured correspondence does not identify evaluator accounts or permissions; do not invent invitations or make the repository public.
3. Verify the registered roster and form answers, including any applicable participation or finalist eligibility details. The saved thread confirms an existing team registration, while later degree/eligibility clarification remains unanswered in the captured material.
4. Submit before **October 30, 2026, 11:59 PM Pacific Time** per the current organizer email. The form labels the time PST; do not assume an extra hour. Save the submission confirmation and the final commit ID.
5. Leave the submitted branch unchanged after freezing it unless Adobe permits corrections. This is our recommended way to keep the evaluated version identifiable. The brief requires submission before code freeze but does not prescribe a Git tag, release, branch lock or commit-ID field. Keep later development separate.

No email, invitation or form submission is authorized by these instructions alone. The current user instruction is to prepare and verify only.

## Unresolved requirements and validation limits

- **Model eligibility:** the brief refers to an approved-model list and size cap that are absent from the captured material. Check any final published restrictions against deployment/model.json. Inference is off by default, but weights and runtime remain in the image. Public access and licensing do not establish eligibility. The sources do not prescribe an individual model-approval email. A required packaging change would need fresh verification before freezing.
- **Evaluator access:** the repository must remain private; the access procedure is not specified in the captured sources. Repository delivery is not established until evaluators can access it through Adobe's chosen process.
- **Reference hardware:** exact final machine limits and actual Mac performance remain unverified. Local WSL/Docker results establish neither Apple Silicon latency nor peak memory there. Testing on that machine is an engineering recommendation, not a stated condition for submitting the form.

No hard stage-one execution-time cutoff is stated in the captured rules. This does not imply unlimited memory or hardware resources. No official quality score, independent held-out aesthetic win or competition rank has been established.

## Clean source package

Use the committed repository revision as the source of truth. A Git source archive includes the engine code, documentation and original brand kit; the Express add-on is removed from the repository and its published branch history. It excludes Git history, local credentials, environments, generated evaluation/audit runs and the outer correspondence workspace. Weights are retrieved and verified during Docker build, not stored in the source archive. This remains a private project package.

The archive is a prepared deliverable, not an uploaded submission. The organizer’s actual access/upload instructions take precedence over any local packaging convention.
