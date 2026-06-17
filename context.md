# NativeCAM Documentation Context

This document serves as the master index and context initialization for the NativeCAM Python 3 / GTK3 port. It maps out the repository's documentation ecosystem to provide a high-level overview for developers and AI assistants.

## 1. Project Overview & Setup
- **[README.md](./README.md)**: Main project introduction, installation instructions (Debian/Source), and basic usage.
- **[INSTALLATION-HELPER.md](./INSTALLATION-HELPER.md)**: Quick-start guide for preparing the environment and running post-installation checks.
- **[GEMINI.md](./GEMINI.md)**: High-level architectural overview, core file mapping, and AI assistant mandates.

## 2. Development Workflow & Standards
- **[DEV-WORKFLOW.md](./DEV-WORKFLOW.md)**: The universal development playbook. Contains the strict 9-phase workflow (Scope -> Verify) and golden rules.
- **[GITHUB-PRACTICES.md](./GITHUB-PRACTICES.md)**: Standards for trunk-based development, Conventional Commits, and PR workflows.

## 3. Planning & Task Management
- **[TASKS.md](./TASKS.md)**: High-level tracking of open points, priorities, and roadmap items.
- **[UPDATE-PLAN.md](./UPDATE-PLAN.md)**: Discrete, phased incremental plans for specific feature goals (e.g., Lathe Polyline, GTK3 hardening).
- **[GTK-MIGRATION.md](./GTK-MIGRATION.md)**: Specific technical debt strategy for migrating legacy `Gtk.Action` to modern `GAction`.
- **LATHE-POLYLINE.md**: Implementation details and coordinate mapping strategies for Lathe polyline support.
- **TURN-MILL-PLANES.md**: Documentation for G17/G18/G19 plane switching required for Lathe live tooling.
- **QTVCP-INTEGRATION.md**: Research and design documentation regarding embedding GTK3 NativeCAM into Qt5/QtVCP environments.

## 4. Knowledge Base & Discoveries
- **LEARNINGS-LOG.md**: An append-only log of technical discoveries, hard-won lessons, and architectural decisions.
- **COMPATIBILITY.md**: Research and findings regarding LinuxCNC 2.10+ compatibility, Wayland vs X11, and XEMBED lifecycle issues.

## 5. Testing & Validation
- **VERIFICATION-GUIDE.md**: Human-in-the-loop testing procedures, focusing on UI stability, G-code syntax correctness, and edge cases.

---
*Note: When starting a new development session, consult `DEV-WORKFLOW.md` and `TASKS.md` first.*