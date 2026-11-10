"""
Local extension sync & install server for Stylus and Violentmonkey.
Provides an interactive Gruvbox dashboard for 1-click installation into extensions,
serves dynamic backups, and serves .user.css and .user.js endpoints with proper headers.
"""

import http.server
import json
import socketserver
import urllib.parse
from pathlib import Path
from typing import Optional

from .extension_manager import ExtensionManager
from .parser import parse_userstyle, parse_userscript


class ExtensionSyncHandler(http.server.SimpleHTTPRequestHandler):
    styles_dir: Path = Path("/home/koresent/Projects/personal/userstyles")
    scripts_dir: Path = Path("/home/koresent/Projects/personal/userscripts")
    ext_manager: Optional[ExtensionManager] = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("", "/", "/dashboard"):
            self.send_dashboard()
        elif path.startswith("/styles/"):
            rel_name = urllib.parse.unquote(path[8:])
            self.serve_file(self.styles_dir / rel_name, "text/css")
        elif path.startswith("/scripts/"):
            rel_name = urllib.parse.unquote(path[9:])
            self.serve_file(self.scripts_dir / rel_name, "application/javascript")
        elif path == "/export/stylus-backup.json":
            self.serve_stylus_backup()
        elif path == "/export/vm-backup.zip":
            self.serve_vm_backup()
        elif path == "/api/status":
            self.serve_api_status()
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, f"File not found: {file_path.name}")
            return

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def serve_stylus_backup(self) -> None:
        if not self.ext_manager:
            self.send_error(500, "Extension manager not initialized")
            return

        temp_json = Path("/tmp/browser_toolkit_stylus_backup.json")
        self.ext_manager.build_stylus_backup_json(self.styles_dir, temp_json)
        self.serve_file(temp_json, "application/json")

    def serve_vm_backup(self) -> None:
        if not self.ext_manager:
            self.send_error(500, "Extension manager not initialized")
            return

        temp_zip = Path("/tmp/browser_toolkit_vm_backup.zip")
        self.ext_manager.build_violentmonkey_backup_zip(self.scripts_dir, temp_zip)
        self.serve_file(temp_zip, "application/zip")

    def serve_api_status(self) -> None:
        styles = list(self.styles_dir.rglob("*.user.css")) if self.styles_dir.exists() else []
        scripts = list(self.scripts_dir.rglob("*.user.js")) if self.scripts_dir.exists() else []

        data = {
            "styles_count": len(styles),
            "scripts_count": len(scripts),
            "styles_dir": str(self.styles_dir),
            "scripts_dir": str(self.scripts_dir),
        }
        raw = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_dashboard(self) -> None:
        styles = sorted(self.styles_dir.rglob("*.user.css")) if self.styles_dir.exists() else []
        scripts = sorted(self.scripts_dir.rglob("*.user.js")) if self.scripts_dir.exists() else []

        style_rows = []
        for s in styles:
            rel = s.relative_to(self.styles_dir)
            info = parse_userstyle(s)
            name = info.name or s.stem
            style_rows.append(f"""
            <tr>
              <td><strong>{name}</strong></td>
              <td><code>{rel}</code></td>
              <td>
                <a class="btn btn-style" href="/styles/{urllib.parse.quote(str(rel))}">
                  📥 Install in Stylus
                </a>
              </td>
            </tr>
            """)

        script_rows = []
        for sc in scripts:
            rel = sc.relative_to(self.scripts_dir)
            info = parse_userscript(sc)
            name = info.name or sc.stem
            version = info.version or "1.0.0"
            script_rows.append(f"""
            <tr>
              <td><strong>{name}</strong> <small style="color:#d5c4a1;">v{version}</small></td>
              <td><code>{rel}</code></td>
              <td>
                <a class="btn btn-script" href="/scripts/{urllib.parse.quote(str(rel))}">
                  ⚡ Install in Violentmonkey
                </a>
              </td>
            </tr>
            """)

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Browser Toolkit — Extension Hub</title>
  <style>
    body {{
      background-color: #282828;
      color: #ebdbb2;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 30px;
    }}
    .container {{
      max-width: 1000px;
      margin: 0 auto;
    }}
    h1 {{ color: #fabd2f; margin-bottom: 5px; }}
    .subtitle {{ color: #a89984; margin-bottom: 25px; }}
    .card {{
      background: #32302f;
      border: 1px solid #504945;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 30px;
    }}
    h2 {{
      color: #b8bb26;
      margin-top: 0;
      border-bottom: 1px solid #504945;
      padding-bottom: 10px;
    }}
    h2.scripts-header {{ color: #83a598; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 15px;
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid #3c3836;
    }}
    th {{ color: #d5c4a1; font-weight: 600; }}
    code {{
      background: #1d2021;
      padding: 3px 6px;
      border-radius: 4px;
      color: #8ec07c;
      font-size: 13px;
    }}
    .btn {{
      display: inline-block;
      padding: 6px 12px;
      border-radius: 5px;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      transition: background 0.2s;
    }}
    .btn-style {{
      background: #b8bb26;
      color: #282828;
    }}
    .btn-style:hover {{ background: #98971a; }}
    .btn-script {{
      background: #83a598;
      color: #282828;
    }}
    .btn-script:hover {{ background: #458588; }}
    .actions-bar {{
      margin-bottom: 20px;
      display: flex;
      gap: 15px;
    }}
    .btn-backup {{
      background: #504945;
      color: #ebdbb2;
      border: 1px solid #665c54;
    }}
    .btn-backup:hover {{ background: #665c54; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>🎨 Browser Toolkit Extension Hub</h1>
    <div class="subtitle">1-Click deploy and automated sync for Stylus and Violentmonkey in Zen Browser</div>

    <div class="actions-bar">
      <a class="btn btn-backup" href="/export/stylus-backup.json" download="stylus-backup.json">
        📦 Download Stylus Backup ({len(styles)} styles)
      </a>
      <a class="btn btn-backup" href="/export/vm-backup.zip" download="vm-backup.zip">
        📦 Download Violentmonkey Backup ({len(scripts)} scripts)
      </a>
    </div>

    <div class="card">
      <h2>Stylus UserStyles ({len(styles)})</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>File</th>
            <th style="width: 180px;">Action</th>
          </tr>
        </thead>
        <tbody>
          {"".join(style_rows) if style_rows else '<tr><td colspan="3" style="color:#a89984;">No styles found in userstyles folder</td></tr>'}
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2 class="scripts-header">Violentmonkey UserScripts ({len(scripts)})</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>File</th>
            <th style="width: 220px;">Action</th>
          </tr>
        </thead>
        <tbody>
          {"".join(script_rows) if script_rows else '<tr><td colspan="3" style="color:#a89984;">No scripts found in userscripts folder</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
        raw = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def run_sync_server(
    port: int = 8080,
    styles_dir: Optional[str | Path] = None,
    scripts_dir: Optional[str | Path] = None,
    profile_path: Optional[str | Path] = None,
) -> None:
    """Launches local extension sync & 1-click install server."""
    s_dir = Path(styles_dir).resolve() if styles_dir else Path("/home/koresent/Projects/personal/userstyles")
    sc_dir = Path(scripts_dir).resolve() if scripts_dir else Path("/home/koresent/Projects/personal/userscripts")

    ExtensionSyncHandler.styles_dir = s_dir
    ExtensionSyncHandler.scripts_dir = sc_dir
    try:
        ExtensionSyncHandler.ext_manager = ExtensionManager(profile_path)
    except Exception as e:
        print(f"Warning: could not initialize ExtensionManager: {e}")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), ExtensionSyncHandler) as httpd:
        print("\n" + "=" * 65)
        print(f"🚀 Extension Hub & 1-Click Server running at: http://127.0.0.1:{port}")
        print(f"📁 Styles directory:  {s_dir}")
        print(f"📁 Scripts directory: {sc_dir}")
        print("-" * 65)
        print("💡 Open in Zen Browser to 1-click install into Stylus & Violentmonkey!")
        print("Press Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
