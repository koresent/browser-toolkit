# browser-toolkit

Automation, inspection, testing, and theme engineering toolkit powered by the **Gecko** engine with native support for **Zen Browser** profiles and active sessions.

Instead of naively generating CSS blindly with templates, this toolkit gives AI agents and developers precise "eyes", "hands", and analytics to build, audit, and debug high-quality userstyles and userscripts based on actual page context, DOM structure, and visual rendering.

---

## 🛠️ Tool Reference

### 1. Site Discovery and Color Analysis
- **`extract-colors <file|url>`**: (Modern evolution of `Extract-ThemeColors-Universal.ps1`)  
  Extracts styles from a stylesheet file or live website, stripping layout grids, spacing, and CSS variable calls to produce a minimal skeleton of selectors and hardcoded colors.
  ```bash
  uv run browser-toolkit extract-colors https://vikunja.io --output vikunja-colors.css
  ```
- **`extract-palette <url>`**:  
  Scans the site for native CSS custom properties (`--color-...`, `--bg-...`) and clusters actual background, text, and border colors by usage frequency.
  ```bash
  uv run browser-toolkit extract-palette https://habr.com
  ```
- **`map-site <url>`**:  
  DOM Structural Fingerprinting algorithm (Jaccard similarity). Crawls the site to identify unique page archetypes (e.g., feed, article card, user profile, settings) while pruning redundant forum threads or posts.
  ```bash
  uv run browser-toolkit map-site https://qna.habr.com --max-archetypes 5
  ```
- **`search <url>`**:  
  Finds elements by text, keywords, or ARIA roles and synthesizes robust selectors (`data-testid`, `aria-*`, stable IDs) instead of fragile hashed CSS module classes.
  ```bash
  uv run browser-toolkit search https://github.com --keyword "copilot"
  ```
- **`inspect <url> --selector <sel>`**:  
  Quickly inspects computed styles, bounding box geometry, and HTML snippet of a target element.

---

### 2. Development, Live Testing, and Hot-Reload
- **`test-rule <url> --css <rule>`**:  
  Tests a CSS hypothesis before modifying the style file. Evaluates visual impact (elements affected, accidental coverage > 25% of viewport) and captures before/after screenshot pairs.
  ```bash
  uv run browser-toolkit test-rule https://github.com --css 'button[aria-label="Open Copilot…"] { display: none !important; }'
  ```
- **`preview <url> <style.user.css>`**:  
  Live Hot-Reload server for styles. Watches the file on disk and injects updated CSS into an open Zen Browser tab in < 20 ms without reloading the page.
  ```bash
  uv run browser-toolkit preview https://habr.com /path/to/gruvbox.user.css
  ```
- **`screenshot <url>`**:  
  Captures screenshots for specific elements (`--selector`), full page (`--full-page`), or on hover (`--hover` for dropdowns and interactive states).
- **`interact <url> --actions <json>`**:  
  Executes user action sequences (`click`, `hover`, `fill`, `wait`, `screenshot`) to inspect modals, tabs, and dynamic states.

---

### 3. Quality Assurance and Auditing
- **`check-responsive <url> [--css <file>] [--screenshots-dir <dir>]`**:  
  Responsive viewport audit across mobile (390x844), tablet (768x1024), and desktop (1440x900). Detects:
  - Horizontal overflow (layout blowout) with exact offending elements, selectors, and computed metrics;
  - Undersized touch targets on mobile (< 24x24px per WCAG 2.5.8);
  - Text clipping (`overflow: hidden` without `text-overflow: ellipsis`);
  - Viewport obstruction by oversized fixed headers or banners (> 30% viewport);
  - Automatically captures screenshots per breakpoint when `--screenshots-dir` is provided.
  ```bash
  uv run browser-toolkit check-responsive https://qna.habr.com --css path/to/style.user.css --screenshots-dir ./screenshots
  ```
- **`check-theme <url> [--css <file>] [--theme dark|light]`**:  
  In-depth theme flaw inspection:
  - White bleedthrough cards, lists, and containers in dark mode;
  - Low contrast / stealth text (< 1.8:1 contrast where background was re-themed but font color was missed);
  - Native unstyled form controls (`<input>`, `<textarea>`, `<select>`) with white backgrounds or unreadable text;
  - Lost SVG icons with dark hardcoded `fill` / `stroke` on dark backgrounds;
  - Native scrollbar styling verification (`scrollbar-color`).
  ```bash
  uv run browser-toolkit check-theme https://qna.habr.com --css path/to/gruvbox.user.css
  ```
- **`check-contrast <url> --css <file>`**:  
  WCAG 2.1 contrast ratio audit (4.5:1 normal text, 3:1 large text). Identifies hard-to-read elements under custom styles with exact foreground and background colors.
  ```bash
  uv run browser-toolkit check-contrast https://qna.habr.com --css path/to/gruvbox.user.css
  ```
- **`audit <file> [--deep-hunt]`**:  
  Audits selector health in `.user.css` or execution in `.user.js` (with GM API polyfills). In `--deep-hunt` mode, crawls across all unique page archetypes until full coverage.
  ```bash
  uv run browser-toolkit audit path/to/gruvbox.user.css --deep-hunt
  ```
- **`scan <dir> [--only-broken]`**:  
  Batch scans entire directories of styles and scripts in a single execution.

---

### 4. UserScript Engineering Tools (.user.js)
- **`test-script <file> [--url <url>] [--command <cmd>] [--actions <json>]`**:  
  Runs userscripts with a full simulation suite of `GM_*` and modern `GM.*` Promise APIs (bypassing CSP):
  - **DOM Mutation Tracking**: records all inserted, removed, or modified nodes and attributes;
  - **Network Request Interception**: logs `GM_xmlhttpRequest` calls (URL, method, status, body, duration);
  - **Menu Command Testing**: triggers any callback registered via `GM_registerMenuCommand` using `--command "Command Name"`;
  - **Clipboard and Notifications**: logs `GM_setClipboard` and `GM_notification` invocations.
  ```bash
  uv run browser-toolkit test-script /path/to/script.user.js --command "Active Forks"
  ```
- **`check-spa <file> <target-spa-url> [--initial-url <url>]`**:  
  Tests script resilience across Single Page Application navigation (GitHub Turbo, YouTube `yt-navigate-finish`, `popstate`, PJAX). Verifies whether custom DOM buttons survive route transitions without handler errors.
  ```bash
  uv run browser-toolkit check-spa /path/to/script.user.js https://github.com/koresent/browser-toolkit
  ```
- **`preview-js <file> [--url <url>]`**:  
  Live Hot-Reload server for userscript development. Reloads the target page in Zen Browser on every file save and prints fresh DOM mutation, network, and console logs.
  ```bash
  uv run browser-toolkit preview-js /path/to/script.user.js
  ```

---

### 5. Extension Management: Stylus and Violentmonkey (`ext`)
Direct programmatic interface to Zen Browser's SQLite / IndexedDB extension databases:
- **`ext status`**:  
  Displays Zen profile path, extension database locations, and installed/active counts.
  ```bash
  uv run browser-toolkit ext status
  ```
- **`ext list-styles [--search <query>]`**:  
  Lists all styles installed in Stylus (status, numeric ID, target domains).
  ```bash
  uv run browser-toolkit ext list-styles --search "habr"
  ```
- **`ext list-scripts [--search <query>]`**:  
  Lists all scripts installed in Violentmonkey (status, numeric ID, version, `@match` rules).
  ```bash
  uv run browser-toolkit ext list-scripts
  ```
- **`ext diff-styles <local_dir>` / `ext diff-scripts <local_dir>`**:  
  Compares local repository files (`.user.css` / `.user.js`) with active extension storage:
  - Detects content discrepancies and out-of-sync edits;
  - Identifies new local files not yet installed in browser;
  - Detects orphan entries installed in browser but missing in git.
  ```bash
  uv run browser-toolkit ext diff-styles /home/koresent/Projects/personal/userstyles
  uv run browser-toolkit ext diff-scripts /home/koresent/Projects/personal/userscripts
  ```
- **`ext export-styles <out_dir>` / `ext export-scripts <out_dir>`**:  
  Exports all styles or scripts directly from extension databases into clean `.user.css` / `.user.js` files on disk.
  ```bash
  uv run browser-toolkit ext export-styles ./dump-styles/
  ```
- **`ext backup [--styles-dir <dir>] [--scripts-dir <dir>]`**:  
  Builds ready-to-import bundles: `stylus-backup.json` (1-click import in Stylus) and `vm-backup.zip` (1-click import in Violentmonkey).
  ```bash
  uv run browser-toolkit ext backup
  ```
- **`ext serve [--port 8080]`**:  
  Local HTTP hub with Gruvbox dashboard providing **1-Click Install** endpoints intercepted natively by Stylus and Violentmonkey.
  ```bash
  uv run browser-toolkit ext serve --port 8080
  ```

- **Programmatic Style Management (Stylus)**:
  - `ext enable-style <ID_or_name>`: Enables an installed style.
  - `ext disable-style <ID_or_name>`: Disables a conflicting style during debugging.
  - `ext toggle-style <ID_or_name>`: Toggles style active state.
  - `ext delete-style <ID_or_name>`: Deletes style from Stylus storage.
  - `ext install-style <path_to_usercss> [--disabled]`: Directly installs or updates a `.user.css` file into Stylus SQLite storage without browser UI interaction.
  ```bash
  uv run browser-toolkit ext disable-style "Discord Gruvbox"
  uv run browser-toolkit ext toggle-style 6
  uv run browser-toolkit ext install-style ./userstyles/habr/habr.user.css
  uv run browser-toolkit ext delete-style "Old Habr Theme"
  ```

- **Programmatic Script Management (Violentmonkey)**:
  - `ext enable-script <ID_or_name>`: Enables an installed script.
  - `ext disable-script <ID_or_name>`: Disables a script to isolate bugs.
  - `ext toggle-script <ID_or_name>`: Toggles script active state.
  - `ext delete-script <ID_or_name>`: Deletes script and associated data (`code`, `mod`, `val`).
  - `ext install-script <path_to_userjs> [--disabled]`: Directly installs or updates a `.user.js` file into Violentmonkey SQLite storage.
  ```bash
  uv run browser-toolkit ext disable-script "YouTube Shorts Redirect"
  uv run browser-toolkit ext toggle-script 1
  uv run browser-toolkit ext install-script ./userscripts/anti-adblock.user.js
  uv run browser-toolkit ext delete-script 18
  ```

---

## Installation

```bash
cd /home/koresent/Projects/personal/browser-toolkit
uv venv
uv pip install -e .
```

All commands support the `--json` flag for seamless programmatic integration with coding agents.
