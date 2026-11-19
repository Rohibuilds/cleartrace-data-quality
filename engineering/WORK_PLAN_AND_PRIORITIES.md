# Work plan for continuing in Antigravity

## Step 0 — preserve real work
- Unzip handoff.
- Ask Antigravity to read it *before* generating replacements.
- If original application files exist, import and audit them.
- Create a safe version-control snapshot; do not force-push or delete an existing repository.

## Step 1 — feature inventory
- Run existing Streamlit prototype, if accessible.
- Compare tested behavior against `spec/COMPLETE_FUNCTIONAL_REQUIREMENTS.md`.
- Mark each requirement: verified / implemented-not-tested / missing / proposed.

## Step 2 — stabilize core
- Ingestion validation and immutable original/working separation.
- Deterministic detectors, proposal objects and revision identifiers.
- Approval-scoped change application; audit trail; undo/reset.
- Correct findings and exports; CSV formula-injection guard.

## Step 3 — visual system
- Use `prompts/02_PREMIUM_UI_DESIGN.md` to generate quality HTML/CSS/JS front-end.
- Keep visual code self-contained, responsive and accessible.
- Separate genuine state from illustrative demo state.

## Step 4 — integration
- Follow `prompts/03_CODEX_INTEGRATION.md`.
- Prefer minimal, safe changes to working Python code; verify every UI action has a real handler.
- Do not use false notifications when backend actions fail.

## Step 5 — test and deliver
- Run automated checks and manual judge demo.
- Record real commands, results, failures and remaining gaps.
- Prepare README, reproducible setup, exports and architecture summary.
- Check hackathon timing/reuse rules prior to submission or public deployment.

## Risk order
1. Incorrect/misleading data mutation.
2. Irreversible changes and weak auditability.
3. Unsafe CSV ingestion/export.
4. Incomplete functionality behind excellent visuals.
5. Fragile event-day demo.
6. Cosmetic polish.

## Boundaries
No actual deployment, working repository, passing tests or full code access is documented here. Those must be established with evidence during continuation.
