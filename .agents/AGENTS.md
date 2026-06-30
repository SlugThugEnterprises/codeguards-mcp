# Audit Rules

## 1. Audit your code separately from vendor code
- Score only first-party code for architecture, style, correctness, and maintainability.
- Treat vendor code as an external dependency surface, not as your product code.

## 5. Separate concerns in audits
- First-party audit: architecture, bugs, tests, maintainability.
- Vendor audit: license, security exposure, version drift, update risk.

## Policy
- Exclude third-party code from your code quality score and refactor plan.
- Do not exclude it from dependency risk review.

## Classification Policy

Only audit code the repo owner is expected to change as part of normal development. Exclude vendor, generated, and build output.

Classify every directory as one of:
1. **First-party code**: Normal source areas (e.g., `src/`, `tests/`, `app/`, `internal/`, `deploy/`, `docs/`) meant to be edited by the project team.
2. **Third-party / vendor code**: Code with its own upstream LICENSE, package manager/upstream build files, foreign project metadata, or that looks copied/vendored from another project (e.g., `vendor/`, `third_party/`, `externals/`, submodules). Treat it as vendor unless explicitly told otherwise.
3. **Generated code / build output**: Artifacts produced by a generator or build step (e.g., `target/`, `dist/`, `build/`, `generated/`, codegen outputs). Always exclude these from quality audits.
4. **Dependency snapshots**: Metadata files like `Cargo.lock`, `package-lock.json`, `pnpm-lock.yaml`. Do not score them for code quality.

### Rule Summary
> “If I didn’t author it as part of this repo’s normal development, don’t score it.”
