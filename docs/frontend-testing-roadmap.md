# Frontend Automation Testing Roadmap

This roadmap tracks the planned rollout of automated testing for the ComfyUI LoRA Manager frontend. Each phase builds on the infrastructure introduced in this change set and records progress so future contributors can quickly identify the next tasks.

## Phase Overview

| Phase | Goal | Primary Focus | Status | Notes |
| --- | --- | --- | --- | --- |
| Phase 0 | Establish baseline tooling | Add Node test runner, jsdom environment, and seed smoke tests | ✅ Complete | Vitest + jsdom configured, example state tests committed |
| Phase 1 | Cover state management logic | Unit test selectors, derived data helpers, and storage utilities under `static/js/state` and `static/js/utils` | 🟡 In Progress | Prioritize deterministic scenarios for `storageHelpers`, `AppState` derivatives, and regression cases for migrations |
| Phase 2 | Test AppCore orchestration | Simulate page bootstrapping, infinite scroll hooks, and manager registration using JSDOM DOM fixtures | ⚪ Not Started | Requires DOM fixtures from `templates/*.html` and stubbing of manager modules |
| Phase 3 | Validate page-specific managers | Add focused suites for `loras`, `checkpoints`, `embeddings`, and `recipes` managers covering filtering, sorting, and bulk actions | ⚪ Not Started | Consider shared helpers for mocking API modules and storage |
| Phase 4 | Interaction-level regression tests | Exercise template fragments, modals, and menus to ensure UI wiring remains intact | ⚪ Not Started | Evaluate Playwright component testing or happy-path DOM snapshots |
| Phase 5 | Continuous integration & coverage | Integrate frontend tests into CI workflow and track coverage metrics | ⚪ Not Started | Align reporting directories with backend coverage for unified reporting |

## Next Steps Checklist

- [ ] Expand unit tests for `storageHelpers` covering migrations and namespace behavior.
- [ ] Document DOM fixture strategy for reproducing template structures in tests.
- [ ] Prototype AppCore initialization test that verifies manager bootstrapping with stubbed dependencies.
- [ ] Evaluate integrating coverage reporting once test surface grows (> 20 specs).

Maintaining this roadmap alongside code changes will make it easier to append new automated test tasks and update their progress.
