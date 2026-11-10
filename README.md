# browser-toolkit

Browser automation, DOM analysis, and extension synchronization toolkit powered by the **Gecko** engine with native **Zen Browser** profile support.

Designed for AI coding agents and developers engineering high-quality **UserStyles** (`.user.css`) and **UserScripts** (`.user.js`).

---

## Quick Start

### Installation

```bash
# Using uv
uv pip install -e .

# Or standard pip
pip install -e .
```

### Agent Instructions
Detailed operating recipes, token-saving TOON format specifications, and extensibility guidelines for autonomous LLM agents are documented in **[AGENTS.md](AGENTS.md)**.

---

## CLI Overview

Run `browser-toolkit --help` or `browser-toolkit <subcommand> --help` for full argument details.

| Command | Description |
|---|---|
| `audit <file>` | Audit selector coverage for `.user.css` or test execution of `.user.js` |
| `scan <dir>` | Batch health scan across a repository of styles and scripts |
| `search <url>` | Synthesize resilient CSS selectors from text, keywords, or ARIA roles |
| `test-rule <url> --css <rule>` | Test candidate CSS rule impact and capture before/after screenshots |
| `extract-palette <url>` | Reverse-engineer native CSS variables and color frequency |
| `extract-colors <target>` | Extract pure CSS color skeleton, stripping layout and fonts |
| `map-site <url>` | Discover unique structural page archetypes (templates) on a website |
| `check-contrast <url>` | Audit WCAG text contrast ratios across styled page |
| `check-theme <url>` | Detect dark theme flaws: bright bleedthrough, unstyled inputs, invisible text |
| `check-responsive <url>` | Audit mobile/tablet responsiveness (overflow blowout, small touch targets) |
| `test-script <file>` | Interactive UserScript testing with GM API polyfills, mutations, and network log |
| `check-spa <file> <url>` | Verify UserScript resilience across client-side SPA route navigations |
| `preview <url> <css>` | Live hot-reload watcher for `.user.css` |
| `preview-js <file>` | Live hot-reload watcher for `.user.js` |
| `screenshot <url>` | Capture viewport or element screenshot with hover/wait options |
| `interact <url>` | Execute automated user action sequences (click, hover, fill) |
| `inspect <url>` | Inspect live element computed styles, geometry, and HTML |
| `ext <action>` | Manage Stylus and Violentmonkey extensions, databases, diffs, and sync hub |

---

## Programmatic Mode & Token Efficiency

All commands support structured, machine-readable output:

```bash
# Output in Token-Oriented Object Notation (TOON) — saves 40-60% tokens for LLMs
browser-toolkit audit style.user.css --toon

# Set global environment variable for agents
export BROWSER_TOOLKIT_FORMAT=toon

# Output in compact JSON
browser-toolkit audit style.user.css --json
```

For extension management, see `browser-toolkit ext --help` or refer to **[AGENTS.md](AGENTS.md)**.
