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
Choose **one** of the following two methods:

* **Method A (Persistent Configuration — Recommended)**:
  Run once at the start of your workflow:
  ```bash
  browser-toolkit config --set-format toon
  ```
  Once set, every subsequent CLI command automatically outputs TOON without requiring `--toon` or environment variables.

* **Method B (Explicit CLI Flag)**:
  Pass `--toon` on each command:
  ```bash
  browser-toolkit <subcommand> [args] --toon
  ```

> [!WARNING]
> **NEVER prepend `export BROWSER_TOOLKIT_FORMAT=toon;` on every single command or combine it with `--toon`**.
> Chaining `export BROWSER_TOOLKIT_FORMAT=toon; browser-toolkit ... --toon` is redundant and wasteful. Set the persistent config once (Method A) or use the `--toon` flag (Method B).

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
* **`search <url> [--text TEXT] [--keyword KW] [--role ROLE] [--tag TAG] [--wait SEL_OR_MS] [--actions JSON] --toon`**  
  Synthesizes resilient CSS selectors scored by stability. Prefers semantic IDs, `data-testid`, and stable class names over obfuscated hashes (`.css-1x2y3z`). Supports `--wait` and pre-search `--actions` for dynamic SPAs.
* **`inspect <url> --selector <sel> [--rules] [--properties PROPS] [--actions JSON] [--css RULE_OR_FILE] [--pseudo PSEUDO] --toon`**  
  Inspects computed styles, bounding box geometry, custom CSS properties (`--var`), and matching stylesheet rules (`--rules`) with optional pre-inspection user actions and candidate CSS injection.
* **`map-site <url> [--max-archetypes N] [--css <path>] --toon`**  
  Uses DOM structural fingerprinting (Jaccard similarity) to discover distinct page templates (home, search, item view, profile) while pruning duplicate forum threads or articles.

### B. Color & Theme Engineering
* **`extract-palette <url> --toon`**  
  Extracts native CSS custom properties (`--color-...`, `--bg-...`) and clusters background, text, and border colors by DOM frequency.
* **`extract-colors [target] [--output PATH] [--clipboard] --toon`**  
  Extracts a minimal CSS color skeleton from a stylesheet file, live URL, or piped standard input (`-`), ranking color swatches by frequency and optionally copying the skeleton to the system clipboard (`-c`).
* **`test-rule <url> --css <rule> --toon`**  
  Tests candidate CSS rule impact on live page without page reload. Flags elements covering >25% viewport and saves before/after screenshots to `/tmp/browser-toolkit/rule-test/`.
* **`check-theme <url> [--css <path>] [--theme dark|light] [--exclude-colors COLORS] --toon`**  
  Detects dark theme flaws (bright bleedthrough, unstyled inputs, invisible text, hidden SVGs, missing scrollbars) and reports dominant surface background/border colors (excluding theme palette colors) so foreign surfaces on natively-dark sites stand out immediately.
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

### G. Browser Automation & Persistent Sessions
* **`screenshot <url> [--selector SEL] [--hover SEL] [--wait SEL] [--full-page] [--output PATH] --toon`**: Capture viewport or element screenshot (defaults to unique timestamped file in `/tmp/browser-toolkit/screenshots/`).
* **`interact <url> --actions <json_or_file> --toon`**: Execute action sequences (`click`, `click_text`, `hover`, `fill`, `press`, `wait`, `wait_for`, `scroll`, `scroll_into_view`, `evaluate`, `evaluate_many`, `screenshot`).
* **`session start [url] [--name ID] [--no-profile] [--profile PATH] [--headful] [--clean-styles] --toon`**: Launches a background session daemon named `ID` (default: `'default'` or `BROWSER_TOOLKIT_SESSION` env var) maintaining an active Playwright instance, Zen profile clone, and open page over `/tmp/browser-toolkit/session_<ID>.sock`. Pass `--clean-styles` to strip installed Stylus styles in the temporary clone while keeping logins/cookies intact. Automatically closes after 15 minutes of inactivity.
* **`session list --toon`**: Lists all active running sessions with their identifiers, current URLs, and uptime.
* **`session status [--name ID] --toon`**: Checks session status, current URL, page title, and uptime.
* **`session frames [--name ID] --toon`**: Lists the main page and all child iframes (including cross-origin iframes) in the active session.
* **`session goto <url> [--name ID] --toon`**: Navigates active session to a URL.
* **`session eval [script] [--file PATH] [--frame FRAME] [--name ID] --toon`**: Evaluates JavaScript expression (inline, `'-'` via stdin, or `--file`) in the active page or specified iframe.
* **`session eval-many <scripts_json_or_file> [--frame FRAME] [--name ID] --toon`**: Evaluates a batch dictionary of JavaScript expressions in one call.
* **`session inspect --selector <sel> [--rules] [--properties PROPS] [--actions JSON] [--css RULE_OR_FILE] [--pseudo PSEUDO] [--frame FRAME] [--name ID] --toon`**: Inspects elements, computed styles, custom properties, and matching CSS rules inside the active session (or target iframe).
* **`session search [--text TEXT] [--keyword KW] [--role ROLE] [--tag TAG] [--wait SEL_OR_MS] [--actions JSON] [--frame FRAME] [--name ID] --toon`**: Searches DOM and synthesizes resilient selectors inside the active session (or target iframe).
* **`session inject-css <css_or_file> [--frame FRAME] [--name ID] --toon`**: Injects a raw CSS snippet or compiled `.user.css` style into the active page or specified iframe.
* **`session check-theme [--css <path>] [--theme dark|light] [--exclude-colors COLORS] [--frame FRAME] [--name ID] --toon`**: Runs `check-theme` inside the live session page or iframe (ideal after opening menus/popups).
* **`session inject-script <file_or_js> [--settle-ms MS] [--name ID] --toon`**: Injects a `.user.js` UserScript or raw JavaScript file into the active session with GM polyfills.
* **`session interact --actions <json_or_file> [--frame FRAME] [--name ID] --toon`**: Executes action sequence in the active session (or target iframe).
* **`session screenshot [--selector SEL] [--output PATH] [--full-page] [--name ID] --toon`**: Captures screenshot from the active session.
* **`session stop [--name ID] --toon`**: Cleanly shuts down daemon, context, and temp profile for session `ID`.

### H. Multi-Agent Concurrency & Isolation
`browser-toolkit` is designed for parallel multi-agent workflows where multiple AI agents work concurrently on different styles and scripts:
* **Zero DOM Collisions**: Standalone commands (`search`, `inspect`, `check-theme`, `check-contrast`, `test-rule`, `audit`) create independent temporary profile clones (`tempfile.mkdtemp`). Multiple agents can inspect different sites concurrently with zero cross-talk.
* **Session Namespaces**: When multiple agents use persistent sessions, each agent must specify a distinct session name (e.g., `session --name tg start ...` or `export BROWSER_TOOLKIT_SESSION=tg`). Use `session list --toon` to discover active sessions across all agents.
* **Thread-Safe Extension DB Writes**: All modifications to Stylus and Violentmonkey databases (`install-style`, `delete-style`, `install-script`, `delete-script`, `enable-*`) are protected by an inter-process file lock (`fcntl.flock`), preventing SQLite database corruption when agents install styles/scripts simultaneously.
* **Safe Artifact Paths**: Screenshots and rule test outputs default to unique timestamped files in `/tmp/browser-toolkit/screenshots/` and `/tmp/browser-toolkit/rule-test/`. Agents should always consume the path reported in `saved_to` or `screenshot_*` rather than assuming a hardcoded filename.

### I. Configuration & Defaults
* **`config [--set-format toon|json|json-pretty|text] [key] [value]`**: Inspects or persists CLI defaults (e.g., `browser-toolkit config --set-format toon` writes to `/tmp/browser-toolkit/default_format`).

---

## 4. Agent Anti-Patterns & Operational Guidelines

Adhere to the following golden rules when reverse-engineering and styling web applications:

### Anti-Pattern 1: Scraping or Grepping Webpack / CDN JavaScript Bundles
* **NEVER** download, fetch, or grep minified CDN script chunks (`index-*.js`, `vendors-*.js`, Webpack runtime bundles).
* SPAs minify, hash, and dynamically chunk code across dozens of files. Grepping raw JavaScript bundles burns thousands of context tokens and yields obsolete, mangled, or unreachable class names.
* **Always search the live rendered DOM**:
  ```bash
  browser-toolkit search <url> --text "Visible Label" --toon
  browser-toolkit search <url> --keyword "search-input" --toon
  ```

### Anti-Pattern 2: Manual Color Guessing Without `extract-palette`
* **NEVER** guess color values or manually hunt through CSS files before inspecting the live palette.
* Always run:
  ```bash
  browser-toolkit extract-palette <url> --toon
  ```
  This immediately clusters colors by DOM frequency and surfaces root CSS custom properties (`--color-...`, `--bg-...`, `--border-...`).

### Anti-Pattern 3: Repeated Cold Browser Launches for Multi-Step Exploration
* **DO NOT** invoke `inspect` or `screenshot` 15 times in a row on the same site if it takes multi-step state setup.
* Instead, start a persistent session with a **distinct, task-specific name** (`--name <id>`):
  ```bash
  browser-toolkit session --name site-auth start "https://example.com" --toon
  browser-toolkit session --name site-auth eval "document.title" --toon
  browser-toolkit session --name site-auth interact --actions '[{"action": "click", "selector": "#menu"}]' --toon
  browser-toolkit session --name site-auth screenshot --selector ".dropdown" --toon
  browser-toolkit session --name site-auth stop --toon
  ```
* **NEVER** use the bare un-named `default` session across parallel agent workflows. Always scope your session by task name (`--name tg-k`, `--name gh-dark`, etc.).

---

## 5. Extensibility Protocol for AI Agents

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
