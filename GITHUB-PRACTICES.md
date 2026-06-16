# GitHub Best Practices for NativeCAM

This document outlines the GitHub standards and workflows adopted for the NativeCAM project to ensure code quality, security, and efficient collaboration.

## 1. Branching Strategy: Trunk-Based Development
*   **Main Branch (`main`):** The primary, stable branch. All releases are cut from here.
*   **Short-Lived Feature Branches:** Create small, focused branches for specific features or fixes (e.g., `feat/lathe-threading`, `fix/gtk-deprecation`).
*   **Frequent Merges:** Aim to merge feature branches back to `main` as quickly as possible to avoid merge conflicts and "integration hell."

## 2. Commit Message Standards: Conventional Commits
Use a standardized format to enable automated changelog generation and easier history browsing:
`<type>(<scope>): <description>`

*   **Types:**
    *   `feat`: A new feature.
    *   `fix`: A bug fix.
    *   `docs`: Documentation changes.
    *   `style`: Formatting, missing semi-colons, etc. (no code changes).
    *   `refactor`: Refactoring production code.
    *   `test`: Adding missing tests, refactoring tests.
    *   `chore`: Updating build tasks, package manager configs, etc.
*   **Example:** `feat(lathe): add G71/G72 roughing cycles`

## 3. Pull Request (PR) Workflow
*   **Draft PRs:** Open PRs as "Draft" early in the development process to signal intent and get early feedback.
*   **Peer Review:** Require at least one approval before merging.
*   **CI Checks:** PRs must pass all CI checks (linting, tests, build) before being merged.
*   **Squash and Merge:** Prefer "Squash and Merge" for feature branches to keep the `main` history clean and atomic.

## 4. Security & Governance
*   **Secret Scanning:** Never commit secrets (API keys, passwords). Enable GitHub secret scanning.
*   **Branch Protection:** Protect the `main` branch to require status checks and reviews.
*   **Dependabot:** Enable Dependabot for security alerts and automated dependency updates.

## 5. CI/CD with GitHub Actions
*   **Automated Linting:** Run linters (e.g., `flake8` for Python) on every push/PR.
*   **Automated Testing:** Execute the full test suite in GitHub Actions.
*   **Build Verification:** Ensure the Debian package build script (`debian/makedeb.sh`) runs successfully in CI.

## 6. Repository Hygiene
*   **README.md:** Keep the README up-to-date with installation, usage, and development setup.
*   **Issue Templates:** Use YAML templates for bug reports and feature requests to gather consistent information.
*   **Labels:** Use clear labels (`bug`, `enhancement`, `priority:high`, etc.) to categorize issues and PRs.

## 7. AI-Assisted Development
*   **Copilot/Gemini CLI:** Leverage AI for boilerplate, documentation, and unit tests, but always verify the output manually.
*   **PR Summaries:** Use AI to generate concise summaries for complex Pull Requests.
