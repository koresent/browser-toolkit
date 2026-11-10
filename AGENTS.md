# AGENTS.md — Browser Toolkit Operational Guide for AI Agents

This document defines the interface, operational principles, tool capabilities, and extensibility protocols for AI coding agents working with **Browser Toolkit**.

---

## 1. Operating Environment & Philosophy

`browser-toolkit` is an autonomous agentic toolkit for inspecting, reverse-engineering, authoring, auditing, and managing **UserStyles** (`.user.css`) and **UserScripts** (`.user.js`).

### Core Environment Constraints
* **Engine**: Firefox / Gecko via Playwright (`p.firefox`). Target browser is Zen Browser.
* **Profile Isolation**: Automatically clones the user's active Zen Browser profile to a temporary sandbox, allowing full access to authentic logins, cookies, localStorage, and extension databases without locking the running browser.
* **Ephemeral Artifacts**: All generated screenshots, reports, and backup archives default to `/tmp/browser-toolkit/`. This keeps the repository workspace completely clean and allows OS cleaner utilities to prune temporary files automatically.
* **Dynamic Agent Composition**: Do not follow hardcoded linear recipes. Select and compose tools dynamically based on the specific problem, observed DOM structure, and failure modes.

---

## 2. Mandatory Output Format for Agents: TOON Only

While `browser-toolkit` supports human-readable text and JSON for developers and shell scripts, **AI AGENTS MUST EXCLUSIVELY USE TOON (`--toon`)**.

### Why TOON is Mandatory for LLMs
* **Context Preservation**: Eliminates repetitive dictionary keys, braces, and redundant quotes, slashing token usage by 40% to 60%.
* **Superior Model Comprehension**: LLM benchmarks demonstrate higher accuracy when parsing uniform objects organized into schema headers and tabular rows.
* **Zero Visual Fluff**: Strips all decorative headers, box-drawing characters, and empty lines that waste tokens.

### Enforcing TOON
Set the environment variable at the beginning of your agent execution session:
```bash
export BROWSER_TOOLKIT_FORMAT=toon
```
When `BROWSER_TOOLKIT_FORMAT=toon` is set, every subcommand automatically outputs TOON without requiring `--toon` on every invocation. If not set, always pass the `--toon` flag explicitly:
```bash
browser-toolkit <subcommand> [args] --toon
```

**Rules for Agents**:
* Never request `--json` or unformatted human text output.
* Never use `pprint.pprint()`, raw `print(dict)`, or `json.dumps()` in helper or scratch scripts to dump massive DOM trees, styling chains, or dictionaries into stdout.
* If generating structured output in helper scripts, serialize it via TOON (`from browser_toolkit.formatters import to_toon`) to preserve context and avoid token exhaustion.

Example TOON output:
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

## 3. Dynamic Tool Catalog

Compose tools dynamically according to the user's goal:

### A. DOM Exploration & Selector Synthesis
* **`search <url> [--text TEXT] [--keyword KW] [--role ROLE] [--tag TAG] --toon`**  
  Synthesizes resilient CSS selectors scored by stability. Prefers semantic IDs, `data-testid`, and stable class names over obfuscated hashes (`.css-1x2y3z`).
* **`inspect <url> --selector <sel> --toon`**  
  Inspects computed styles, bounding box geometry, and outer HTML snippet of live elements.
* **`map-site <url> [--max-archetypes N] [--css <path>] --toon`**  
  Uses DOM structural fingerprinting (Jaccard similarity) to discover distinct page templates (home, search, item view, profile) while pruning duplicate forum threads or articles.

### B. Color & Theme Engineering
* **`extract-palette <url> --toon`**  
  Extracts native CSS custom properties (`--color-...`, `--bg-...`) and clusters background, text, and border colors by DOM frequency.
* **`extract-colors <target> [--output PATH]`**  
  Extracts a minimal CSS color skeleton from a stylesheet or URL, discarding layout, grid, and font rules.
* **`test-rule <url> --css <rule> --toon`**  
  Tests candidate CSS rule impact on live page without page reload. Flags elements covering >25% viewport and saves before/after screenshots to `/tmp/browser-toolkit/rule-test/`.
* **`check-theme <url> [--css <path>] [--theme dark|light] --toon`**  
  Detects dark theme flaws: bright background bleedthrough, unstyled native inputs, invisible text (WCAG contrast < 1.8:1), hidden SVG icons, and missing scrollbar styling.
* **`check-contrast <url> [--css <path>] --toon`**  
  Audits WCAG text contrast ratios across all visible text nodes on the styled page.

### C. Responsive Layout Auditing
* **`check-responsive <url> [--css <path>] [--viewports WxH,WxH] --toon`**  
  Audits mobile, tablet, and desktop viewports for horizontal overflow blowout, touch targets under 24x24px, and clipped text. Screenshots saved to `/tmp/browser-toolkit/responsive/`.

### D. UserScript Simulation & Verification
* **`audit <script.user.js> [--url <url>] --toon`**  
  Executes script with modern GM API polyfills (`GM_setValue`, `GM_xmlhttpRequest`, `GM_setClipboard`, `GM_registerMenuCommand`). Tracks DOM mutations, network requests, and errors.
* **`test-script <script.user.js> [--command <cmd>] [--actions <json>] --toon`**  
  Interactive script test invoking menu commands and user action sequences.
* **`check-spa <script.user.js> <target_url> [--initial-url <url>] --toon`**  
  Simulates client-side SPA route transitions (Turbo, Next.js, YouTube) and verifies that injected elements persist or re-mount without errors.

### E. Extension Management (Stylus & Violentmonkey)
Direct programmatic access to browser extension state via IndexedDB:
* **`ext status --toon`**: Profile path, database files, and active style/script counts.
* **`ext list-styles [--search Q] --toon`**: List installed Stylus styles with enabled state and domains.
* **`ext list-scripts [--search Q] --toon`**: List installed Violentmonkey scripts with versions and matches.
* **`ext install-style <file.user.css> [--disabled] --toon`**: Install or update style in Stylus.
* **`ext install-script <file.user.js> [--disabled] --toon`**: Install or update script in Violentmonkey.
* **`ext enable-style <target> --toon`** / **`ext disable-style <target> --toon`**: Toggle style on/off.
* **`ext toggle-style <target> --toon`**: Invert style enabled status.
* **`ext delete-style <target> --toon`**: Remove style from Stylus.
* **`ext enable-script <target> --toon`** / **`ext disable-script <target> --toon`**: Toggle script on/off.
* **`ext toggle-script <target> --toon`**: Invert script enabled status.
* **`ext delete-script <target> --toon`**: Remove script from Violentmonkey.
* **`ext diff-styles <local_dir> --toon`**: Diff local repository files against active Stylus database.
* **`ext diff-scripts <local_dir> --toon`**: Diff local repository files against active Violentmonkey database.
* **`ext backup [--out-stylus PATH] [--out-vm PATH] --toon`**: Build ready-to-import backup bundles in `/tmp/browser-toolkit/`.
* **`ext export-styles <dir>`** / **`ext export-scripts <dir>`**: Export database records as clean source files.
* **`ext serve [--port 8080]`**: Launch local 1-click install & sync server hub.

### F. Repository Scanning & Live Watchers
* **`scan <dir> [--only-broken] --toon`**: Batch health audit across all `.user.css` and `.user.js` files in a folder.
* **`preview <url> <style.user.css>`**: Live hot-reload watcher injecting CSS in <20ms without page refresh.
* **`preview-js <script.user.js>`**: Live hot-reload watcher for scripts.

### G. Browser Automation
* **`screenshot <url> [--selector SEL] [--hover SEL] [--wait SEL] [--full-page] --toon`**: Capture viewport or element screenshot to `/tmp/browser-toolkit/screenshot.png`.
* **`interact <url> --actions <json_or_file> --toon`**: Execute action sequences (click, hover, fill, wait).

---

## 4. Extensibility Protocol for AI Agents

When modifying or extending `browser-toolkit`, agents must adhere to the following rules:

### Rule 1: The Recurring-Need Gate (Anti-Bloat Filter)
* **DO NOT** add new CLI commands or permanent modules for one-off tasks.
* **DO NOT re-implement browser-toolkit capabilities in scratch scripts**: Never write ad-hoc Playwright scripts that duplicate existing CLI commands (`inspect`, `search`, `test-rule`, `check-theme`, `screenshot`, `extract-palette`, etc.). The CLI is already battle-tested for profile cloning, redirect resilience, and token efficiency.
* Ephemeral scratch scripts in the conversation's scratch directory are reserved **ONLY** for genuine one-off tasks that cannot be accomplished with existing CLI commands.
* A permanent tool is justified **ONLY** when:
  1. The functionality solves a recurring browser engineering problem across at least 3 distinct sites or styles/scripts.
  2. The capability cannot be composed cleanly from existing subcommands.

### Rule 2: Language & Comment Hygiene
* **100% English**: All code, docstrings, CLI help strings, and comments must be strictly in English. Zero non-English characters in tracked files.
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

### Rule 5: Artifact Hygiene & Data Security
* All generated artifacts (screenshots, reports, dumps) must default to `/tmp/browser-toolkit/`.
* Never commit secrets, tokens, cookies, or hardcoded user home paths (`/home/...`). Always resolve paths dynamically using `Path.home()`.
* Never commit generated artifacts or backups. Verify `.gitignore` before staging.
