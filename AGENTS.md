# AGENTS.md — Browser Toolkit Operational Guide for AI Agents

This document defines the interface, operational workflows, and extension protocols for AI coding agents (such as Antigravity, Claude Code, and other autonomous LLM agents) working with **Browser Toolkit**.

---

## 1. Operating Environment & Philosophy

`browser-toolkit` is designed for autonomous agentic inspection, live reverse-engineering, authoring, auditing, and extension management for **UserStyles** (`.user.css`) and **UserScripts** (`.user.js`).

### Core Environment Constraints
* **Engine**: Firefox / Gecko via Playwright (`p.firefox`). Target browser is Zen Browser.
* **Profile Isolation**: Automatically clones the user's active Zen Browser profile to a temporary sandbox, allowing full access to authentic sessions, cookies, localStorage, and extension databases without locking the running browser.
* **Token Efficiency First**: Agents must avoid verbose, decorative console output. Use structured formats (`--toon` or `--json`) to minimize token consumption and keep context windows compact.

---

## 2. Mandatory Output Format for Agents: TOON Only

While `browser-toolkit` supports human-readable text and JSON for developers and external shell scripts, **AI AGENTS MUST EXCLUSIVELY USE TOON (`--toon`)**.

### Why TOON is Mandatory for LLMs
* **Context Preservation**: Eliminates repetitive dictionary keys, braces, and redundant quotes, slashing token usage by 40% to 60%.
* **Superior Model Comprehension**: LLM benchmarks demonstrate higher accuracy when parsing uniform objects organized into schema headers and tabular rows.
* **Zero Visual Fluff**: Strips all decorative headers, box-drawing characters, and empty lines that waste tokens.

### Enforcing TOON
Set the environment variable at the beginning of your agent execution session:
```bash
export BROWSER_TOOLKIT_FORMAT=toon
```
When `BROWSER_TOOLKIT_FORMAT=toon` is set, every subcommands automatically outputs TOON without requiring `--toon` on every invocation. If not set, always pass the `--toon` flag explicitly:
```bash
browser-toolkit <subcommand> [args] --toon
```

**Rule for Agents**: Never request `--json` or unformatted human text output.

Example TOON audit output:
```yaml
type: userstyle
name: GitHub Gruvbox
target_url: "https://github.com"
total_selectors: 120
matched: 115
dead: 5
dead_selectors[5]{selector,reason}:
  .header-search-input,element_not_found
  .repo-pjax-container,element_not_found
```

---

## 3. Standard Agent Workflows

### Workflow A: Live Site Reconnaissance & Color Extraction
Before writing or modifying a theme:
1. **Map structural archetypes** across the target domain:
   ```bash
   browser-toolkit map-site https://example.com --max-archetypes 5 --toon
   ```
2. **Reverse engineer page palette & CSS custom properties**:
   ```bash
   browser-toolkit extract-palette https://example.com --toon
   ```
3. **Extract pure CSS color skeleton** (discarding layouts/fonts):
   ```bash
   browser-toolkit extract-colors https://example.com --output ./skeleton.css
   ```

### Workflow B: Selector Discovery & Synthesis
When finding elements to theme or script without manually guessing classes:
1. **Synthesize resilient selectors**:
   ```bash
   browser-toolkit search https://example.com --text "Submit Order" --tag button --toon
   browser-toolkit search https://example.com --keyword "navbar" --toon
   ```
   *The synthesizer prioritizes semantic IDs, `data-testid`, and stable class names over dynamic/obfuscated hashes (e.g. `.css-1x2y3z`).*

### Workflow C: Safe Rule Testing & Impact Analysis
Before modifying the user's stylesheet:
1. **Test candidate CSS rule impact on live page**:
   ```bash
   browser-toolkit test-rule https://example.com --css ".header { background-color: #282828 !important; }" --toon
   ```
   *Reports matched elements, viewport coverage ratio (>25% flagged as high-impact), and saves before/after screenshots.*

### Workflow D: Visual Flaw & Accessibility Auditing
1. **Check dark/light theme flaws**:
   ```bash
   browser-toolkit check-theme https://example.com --css ./style.user.css --theme dark --toon
   ```
   *Audits for bright background bleedthrough in dark mode, unstyled native `<input>` fields, invisible text (contrast ratio < 1.8:1), hidden SVG icons, and missing scrollbar theming.*
2. **Audit responsive layout**:
   ```bash
   browser-toolkit check-responsive https://example.com --css ./style.user.css --toon
   ```
   *Tests across mobile, tablet, and desktop viewports for horizontal overflow blowout, touch targets under 24x24px, and clipped text.*

### Workflow E: UserScript Auditing & SPA Resilience
1. **Audit script with GM polyfill shim**:
   ```bash
   browser-toolkit audit ./script.user.js --toon
   ```
   *Simulates GM API (`GM_setValue`, `GM_xmlhttpRequest`, `GM_setClipboard`), tracks DOM mutations, network requests, and console errors.*
2. **Interactive script testing with user actions**:
   ```bash
   browser-toolkit test-script ./script.user.js --command "Toggle Dark Mode" --toon
   ```
3. **Verify resilience across SPA route navigations**:
   ```bash
   browser-toolkit check-spa ./script.user.js "https://github.com/org/repo" --toon
   ```
   *Simulates client-side transitions (Turbo, Next.js, YouTube) and verifies that injected UI elements persist or re-mount.*

### Workflow F: Programmatic Extension Management (Stylus & Violentmonkey)
Agents can inspect and mutate extension state directly:
1. **Check extension status**:
   ```bash
   browser-toolkit ext status --toon
   ```
2. **List and search installed items**:
   ```bash
   browser-toolkit ext list-styles --search "github" --toon
   browser-toolkit ext list-scripts --search "youtube" --toon
   ```
3. **Install or update styles/scripts**:
   ```bash
   browser-toolkit ext install-style ./github.user.css --toon
   browser-toolkit ext install-script ./enhancer.user.js --toon
   ```
4. **Toggle or delete styles/scripts**:
   ```bash
   browser-toolkit ext toggle-style "GitHub Gruvbox" --toon
   browser-toolkit ext delete-script "Old Script" --toon
   ```
5. **Diff local repository files against browser database**:
   ```bash
   browser-toolkit ext diff-styles ~/Projects/personal/userstyles --toon
   browser-toolkit ext diff-scripts ~/Projects/personal/userscripts --toon
   ```
6. **Launch local 1-click sync server**:
   ```bash
   browser-toolkit ext serve --port 8080
   ```

---

## 4. Extensibility Protocol for AI Agents

Agents modifying or extending `browser-toolkit` must adhere to the following rigid rules.

### Rule 1: The Recurring-Need Gate (Anti-Bloat Filter)
* **DO NOT** add new CLI commands, modules, or permanent features for one-off or two-off tasks.
* If a task is specific to a single site edge-case or only needed once, write an ephemeral scratch script in the conversation's scratch directory.
* A permanent tool is justified **ONLY** when:
  1. The functionality solves a recurring browser engineering problem across at least 3 distinct sites or styles/scripts.
  2. The capability cannot be composed cleanly from existing subcommands.

### Rule 2: Language & Comment Hygiene
* **100% English**: All code, docstrings, CLI help messages, and comments must be strictly in English. Zero non-English characters in tracked files.
* **Antislop Comment Standards**:
  * Never use decorative comment borders (`// ====================`, `/* ---------- */`, `# ----------------`).
  * Never use step-by-step workflow narration (`# 1. Initialize`, `// 2. Fetch data`, `# 3. Return report`).
  * Never restate obvious signatures (`# audit_style audits style`).
  * Only document protocol quirks, Gecko/Chromium divergence, browser security boundaries, or non-obvious algorithms (e.g. WCAG contrast relative luminance formulas).

### Rule 3: Conventional Commits & Neutral Messages
* Commit messages must follow conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
* Keep commit messages neutral, technical, and descriptive.
* **NEVER** use internal prompt buzzwords (such as "antislop") in commit messages or repository files.

### Rule 4: Mandatory Automated Tests
* Any new module or modified command **MUST** include automated tests in `tests/`.
* Before committing, execute the entire test suite:
  ```bash
  .venv/bin/python -m unittest discover tests
  ```
  All tests must pass cleanly.

### Rule 5: Git Hygiene & Data Security
* Never commit secrets, tokens, cookies, or hardcoded user home paths (`/home/...`). Always resolve paths dynamically using `Path.home()`.
* Never commit generated artifacts: screenshots (`*.png`, `*.jpg`), SQLite database backups (`*.sqlite.bak`), extension backup archives (`*.json`, `*.zip`), or debug logs. Verify `.gitignore` before staging.
