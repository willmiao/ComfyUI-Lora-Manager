# Frontend Automation Testing Roadmap

This roadmap tracks the planned rollout of automated testing for the ComfyUI LoRA Manager frontend. Each phase builds on the infrastructure introduced in this change set and records progress so future contributors can quickly identify the next tasks.

## Phase Overview

| Phase | Goal | Primary Focus | Status | Notes |
| --- | --- | --- | --- | --- |
| Phase 0 | Establish baseline tooling | Add Node test runner, jsdom environment, and seed smoke tests | ✅ Complete | Vitest + jsdom configured, example state tests committed |
| Phase 1 | Cover state management logic | Unit test selectors, derived data helpers, and storage utilities under `static/js/state` and `static/js/utils` | ✅ Complete | Storage helpers and state selectors now exercised via deterministic suites |
| Phase 2 | Test AppCore orchestration | Simulate page bootstrapping, infinite scroll hooks, and manager registration using JSDOM DOM fixtures | ✅ Complete | AppCore initialization + page feature suites now validate manager wiring, infinite scroll hooks, and onboarding gating |
| Phase 3 | Validate page-specific managers | Add focused suites for `loras`, `checkpoints`, `embeddings`, and `recipes` managers covering filtering, sorting, and bulk actions | ✅ Complete | LoRA/checkpoint suites expanded; embeddings + recipes managers now covered with initialization, filtering, and duplicate workflows |
| Phase 4 | Interaction-level regression tests | Exercise template fragments, modals, and menus to ensure UI wiring remains intact | ✅ Complete | Vitest DOM suites cover NSFW selector, recipe modal editing, and global context menus |
| Phase 5 | Continuous integration & coverage | Integrate frontend tests into CI workflow and track coverage metrics | ✅ Complete | CI workflow runs Vitest and aggregates V8 coverage into `coverage/frontend` via a dedicated script |

## Next Steps Checklist

- [x] Expand unit tests for `storageHelpers` covering migrations and namespace behavior.
- [x] Document DOM fixture strategy for reproducing template structures in tests.
- [x] Prototype AppCore initialization test that verifies manager bootstrapping with stubbed dependencies.
- [x] Add AppCore page feature suite exercising context menu creation and infinite scroll registration via DOM fixtures.
- [x] Extend AppCore orchestration tests to cover manager wiring, bulk menu setup, and onboarding gating scenarios.
- [x] Add interaction regression suites for context menus and recipe modals to complete Phase 4.
- [x] Evaluate integrating coverage reporting once test surface grows (> 20 specs).
- [x] Create shared fixtures for the loras and checkpoints pages once dedicated manager suites are added.
- [x] Draft focused test matrix for loras/checkpoints manager filtering and sorting paths ahead of Phase 3.
- [x] Implement LoRAs manager filtering/sorting specs for scenarios F-01–F-05 & F-09; queue remaining edge cases after duplicate/bulk flows stabilize.
- [x] Implement checkpoints manager filtering/sorting specs for scenarios F-01–F-05 & F-09; cover remaining paths alongside bulk action work.
- [x] Implement checkpoints page manager smoke tests covering initialization and duplicate badge wiring.
- [x] Outline focused checkpoints scenarios (filtering, sorting, duplicate badge toggles) to feed into the shared test matrix.
- [ ] Add duplicate badge regression coverage for zero/pending states after API refreshes.

Maintaining this roadmap alongside code changes will make it easier to append new automated test tasks and update their progress.
