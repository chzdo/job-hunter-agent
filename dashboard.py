import os
import json
import yaml
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime
import http.server
import socketserver

from database import get_stats, get_jobs_by_status

logger = logging.getLogger("job_hunter.dashboard")
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESUMES_DIR = BASE_DIR / "resumes"
DATA_DIR = BASE_DIR / "data"
DASHBOARD_FILE = DATA_DIR / "dashboard.html"

EXECUTION_STATE = {
    "is_running": False,
    "last_run": None,
    "last_result": None
}

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}

def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

def run_cycle_thread():
    global EXECUTION_STATE
    if EXECUTION_STATE["is_running"]:
        return
    EXECUTION_STATE["is_running"] = True
    try:
        from scheduler import run_job_cycle
        cfg = load_config()
        run_job_cycle(cfg, dry_run=False)
        EXECUTION_STATE["last_result"] = "Success"
    except Exception as e:
        logger.error(f"Cycle execution failed: {e}", exc_info=True)
        EXECUTION_STATE["last_result"] = f"Error: {e}"
    finally:
        EXECUTION_STATE["is_running"] = False
        EXECUTION_STATE["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def render_dashboard_html() -> str:
    """Generate interactive HTML dashboard with role selector, locations, job type, and CV preview."""
    cfg = load_config()
    stats = get_stats()
    roles = cfg.get("search", {}).get("roles", [])
    locations = cfg.get("search", {}).get("locations", ["Nigeria"])
    job_type = cfg.get("search", {}).get("job_type", "both")
    resumes = cfg.get("resumes", {})
    email_cfg = cfg.get("email_notifications", {})

    jobs = []
    for s in ["APPLIED", "QUEUED", "DISCOVERED", "SKIPPED", "FAILED"]:
        jobs.extend(get_jobs_by_status(s, limit=25))
    jobs.sort(key=lambda j: j.get("applied_at") or j.get("created_at") or "", reverse=True)

    job_rows = []
    for j in jobs[:60]:
        status = j.get("status", "DISCOVERED")
        badge_class = f"badge-{status.lower()}"
        job_rows.append(f"""
        <tr>
            <td><span class="badge {badge_class}">{status}</span></td>
            <td><strong>{j.get('site', 'N/A').capitalize()}</strong></td>
            <td>{j.get('title', 'N/A')}</td>
            <td>{j.get('company', 'N/A')}</td>
            <td>{j.get('location', 'N/A')}</td>
            <td><a class="job-link" href="{j.get('job_url', '#')}" target="_blank">View Listing ↗</a></td>
        </tr>
        """)

    roles_json = json.dumps(roles)
    locations_json = json.dumps(locations)
    job_type_json = json.dumps(job_type)
    resumes_json = json.dumps(resumes)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Hunter Agent - Command & Control Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --border: #334155;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #818cf8;
            --btn-bg: #2563eb;
            --btn-hover: #1d4ed8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }}
        body {{ background: var(--bg); color: var(--text-primary); padding: 2rem; max-width: 1400px; margin: auto; }}
        
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
        .header h1 {{ font-size: 1.8rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem; }}
        .header-actions {{ display: flex; gap: 1rem; align-items: center; }}
        
        button.btn-primary {{
            background: var(--btn-bg); color: #fff; border: none; padding: 0.75rem 1.4rem;
            border-radius: 8px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 0.5rem;
            transition: all 0.2s;
        }}
        button.btn-primary:hover {{ background: var(--btn-hover); transform: translateY(-1px); }}
        button.btn-primary:disabled {{ background: #475569; cursor: not-allowed; transform: none; }}

        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; }}
        .card-title {{ color: var(--text-secondary); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; }}
        .card-value {{ font-size: 2rem; font-weight: 700; margin-top: 0.4rem; }}
        .card.applied .card-value {{ color: var(--success); }}
        .card.discovered .card-value {{ color: var(--accent); }}
        .card.queued .card-value {{ color: var(--warning); }}
        .card.skipped .card-value {{ color: var(--info); }}
        .card.failed .card-value {{ color: var(--danger); }}

        .management-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 1.5rem; margin-bottom: 2.5rem; }}

        .panel {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; justify-content: space-between; }}
        .panel-title {{ font-size: 1.15rem; font-weight: 600; margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between; }}

        .tag-list {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; min-height: 48px; }}
        .tag-item {{ background: #334155; padding: 0.4rem 0.8rem; border-radius: 9999px; font-size: 0.85rem; display: flex; align-items: center; gap: 0.5rem; }}
        .tag-item span.remove {{ cursor: pointer; color: #f87171; font-weight: bold; font-size: 1rem; }}
        .tag-item span.remove:hover {{ color: #ef4444; }}

        .input-group {{ display: flex; gap: 0.5rem; }}
        .input-group input, .input-group select {{
            background: #0f172a; border: 1px solid var(--border); color: #fff; padding: 0.6rem 0.8rem;
            border-radius: 6px; font-size: 0.9rem; flex: 1;
        }}
        .input-group button {{
            background: #334155; border: 1px solid var(--border); color: #fff; padding: 0.6rem 1rem;
            border-radius: 6px; cursor: pointer; font-weight: 500;
        }}
        .input-group button:hover {{ background: #475569; }}

        .cv-table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.88rem; }}
        .cv-table th, .cv-table td {{ padding: 0.6rem; border-bottom: 1px solid var(--border); text-align: left; }}
        .cv-table th {{ color: var(--text-secondary); }}

        .table-container {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow-x: auto; }}
        table.jobs-table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 0.92rem; }}
        table.jobs-table th {{ background: #111827; padding: 0.9rem; color: var(--text-secondary); border-bottom: 1px solid var(--border); }}
        table.jobs-table td {{ padding: 0.9rem; border-bottom: 1px solid var(--border); }}
        table.jobs-table tr:hover {{ background: rgba(255, 255, 255, 0.02); }}

        .badge {{ display: inline-block; padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }}
        .badge-applied {{ background: rgba(16, 185, 129, 0.2); color: var(--success); }}
        .badge-discovered {{ background: rgba(56, 189, 248, 0.2); color: var(--accent); }}
        .badge-queued {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); }}
        .badge-skipped {{ background: rgba(129, 140, 248, 0.2); color: var(--info); }}
        .badge-failed {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); }}
        a.job-link {{ color: var(--accent); text-decoration: none; font-weight: 500; }}
        a.job-link:hover {{ text-decoration: underline; }}
        
        .toast {{
            position: fixed; bottom: 20px; right: 20px; background: #10b981; color: #fff;
            padding: 1rem 1.5rem; border-radius: 8px; font-weight: 600; display: none; z-index: 100;
        }}
    </style>
</head>
<body>
    <div id="toast" class="toast">Action Saved!</div>

    <div class="header">
        <div>
            <h1>🤖 Job Hunter Agent</h1>
            <div style="color: var(--text-secondary); font-size: 0.9rem; margin-top: 0.3rem;">
                Autonomous Multi-Platform Scheduler • Next auto-run in 12h • Notification: {email_cfg.get('recipient_email', 'chido.nduaguibe@gmail.com')}
            </div>
        </div>
        <div class="header-actions">
            <span id="running-indicator" style="display: {'inline' if EXECUTION_STATE['is_running'] else 'none'}; color: var(--warning); font-size: 0.9rem; font-weight: 600;">
                ⏳ Cycle in progress...
            </span>
            <button id="trigger-btn" class="btn-primary" onclick="triggerCycle()" {'disabled' if EXECUTION_STATE['is_running'] else ''}>
                🚀 Run Search & Apply Now
            </button>
        </div>
    </div>

    <!-- Metrics -->
    <div class="stats-grid">
        <div class="card discovered">
            <div class="card-title">Total Discovered</div>
            <div class="card-value">{stats.get('DISCOVERED', 0) + stats.get('TOTAL', 0)}</div>
        </div>
        <div class="card applied">
            <div class="card-title">Successfully Applied</div>
            <div class="card-value">{stats.get('APPLIED', 0)}</div>
        </div>
        <div class="card queued">
            <div class="card-title">Queued / Review</div>
            <div class="card-value">{stats.get('QUEUED', 0)}</div>
        </div>
        <div class="card skipped">
            <div class="card-title">Skipped</div>
            <div class="card-value">{stats.get('SKIPPED', 0)}</div>
        </div>
        <div class="card failed">
            <div class="card-title">Blocked / Failed</div>
            <div class="card-value">{stats.get('FAILED', 0)}</div>
        </div>
    </div>

    <!-- Management Panels -->
    <div class="management-grid">
        <!-- 1. Target Roles -->
        <div class="panel">
            <div>
                <div class="panel-title">
                    <span>🎯 Target Job Roles</span>
                    <button onclick="saveRoles()" style="background:none; border:1px solid var(--accent); color:var(--accent); padding:0.3rem 0.7rem; border-radius:6px; cursor:pointer; font-size:0.8rem;">Save Roles</button>
                </div>
                <div id="roles-container" class="tag-list"></div>
            </div>
            <div class="input-group">
                <input type="text" id="new-role-input" placeholder="e.g. Senior QA Engineer, DevOps..." onkeypress="if(event.key==='Enter') addRole()">
                <button type="button" onclick="addRole()">+ Add Role</button>
            </div>
        </div>

        <!-- 2. Target Locations & Job Type -->
        <div class="panel">
            <div>
                <div class="panel-title">
                    <span>🌍 Locations & Workplace Type</span>
                    <button onclick="saveLocationSettings()" style="background:none; border:1px solid var(--accent); color:var(--accent); padding:0.3rem 0.7rem; border-radius:6px; cursor:pointer; font-size:0.8rem;">Save Settings</button>
                </div>
                <div id="locations-container" class="tag-list"></div>
                <div class="input-group" style="margin-bottom: 1rem;">
                    <input type="text" id="new-location-input" placeholder="Add location (e.g. Lagos, Abuja, Remote)..." onkeypress="if(event.key==='Enter') addLocation()">
                    <button type="button" onclick="addLocation()">+ Add Location</button>
                </div>
            </div>
            <div>
                <label style="font-size:0.85rem; color:var(--text-secondary); display:block; margin-bottom:0.4rem; font-weight:600;">Workplace Type Preference:</label>
                <div class="input-group">
                    <select id="job-type-select">
                        <option value="both">Both (Remote & On-site / Hybrid)</option>
                        <option value="remote">Remote Only</option>
                        <option value="hybrid">Hybrid Only</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- 3. Tailored CV Mapping & Viewer -->
        <div class="panel" style="grid-column: 1 / -1;">
            <div>
                <div class="panel-title">
                    <span>📄 Tailored CVs & Live Preview</span>
                </div>
                <p style="color:var(--text-secondary); font-size:0.85rem; margin-bottom:0.8rem;">
                    Upload a tailored CV for each role. You can click <strong>View / Download</strong> anytime to verify your PDF!
                </p>
                <div class="input-group" style="margin-bottom: 1rem;">
                    <select id="cv-role-select" style="max-width:240px;"></select>
                    <input type="file" id="cv-file-input" accept=".pdf" style="padding:0.4rem;">
                    <button type="button" onclick="uploadResume()">Upload & Assign CV</button>
                </div>
            </div>
            <table class="cv-table">
                <thead>
                    <tr>
                        <th>Job Role</th>
                        <th>Assigned CV File</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="cv-mapping-body"></tbody>
            </table>
        </div>
    </div>

    <!-- Live Jobs Table -->
    <div class="panel-title" style="margin-top: 1rem;">📋 Real-Time Job Opportunities & Application History</div>
    <div class="table-container">
        <table class="jobs-table">
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Platform</th>
                    <th>Job Title</th>
                    <th>Company</th>
                    <th>Location</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {''.join(job_rows) if job_rows else "<tr><td colspan='6' style='text-align:center;'>No jobs discovered yet. Click 'Run Search & Apply Now'!</td></tr>"}
            </tbody>
        </table>
    </div>

    <script>
        let currentRoles = {roles_json};
        let currentLocations = {locations_json};
        let currentJobType = {job_type_json};
        let currentResumes = {resumes_json};

        function showToast(msg) {{
            const t = document.getElementById("toast");
            t.innerText = msg;
            t.style.display = "block";
            setTimeout(() => {{ t.style.display = "none"; }}, 3000);
        }}

        // Roles Management
        function renderRoles() {{
            const container = document.getElementById("roles-container");
            container.innerHTML = "";
            currentRoles.forEach((r, idx) => {{
                const tag = document.createElement("div");
                tag.className = "tag-item";
                tag.innerHTML = `<span>${{r}}</span><span class="remove" onclick="removeRole(${{idx}})">×</span>`;
                container.appendChild(tag);
            }});
            renderRoleDropdown();
        }}

        function addRole() {{
            const inp = document.getElementById("new-role-input");
            const val = inp.value.trim();
            if (val && !currentRoles.includes(val)) {{
                currentRoles.push(val);
                inp.value = "";
                renderRoles();
            }}
        }}

        function removeRole(idx) {{
            currentRoles.splice(idx, 1);
            renderRoles();
        }}

        function saveRoles() {{
            fetch("/api/roles", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{ roles: currentRoles }})
            }}).then(res => res.json()).then(data => {{
                showToast("✅ Target roles updated & saved!");
            }});
        }}

        // Locations & Job Type Management
        function renderLocations() {{
            const container = document.getElementById("locations-container");
            container.innerHTML = "";
            currentLocations.forEach((loc, idx) => {{
                const tag = document.createElement("div");
                tag.className = "tag-item";
                tag.innerHTML = `<span>${{loc}}</span><span class="remove" onclick="removeLocation(${{idx}})">×</span>`;
                container.appendChild(tag);
            }});
            document.getElementById("job-type-select").value = currentJobType;
        }}

        function addLocation() {{
            const inp = document.getElementById("new-location-input");
            const val = inp.value.trim();
            if (val && !currentLocations.includes(val)) {{
                currentLocations.push(val);
                inp.value = "";
                renderLocations();
            }}
        }}

        function removeLocation(idx) {{
            currentLocations.splice(idx, 1);
            renderLocations();
        }}

        function saveLocationSettings() {{
            const jType = document.getElementById("job-type-select").value;
            currentJobType = jType;
            fetch("/api/search-settings", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{ locations: currentLocations, job_type: jType }})
            }}).then(res => res.json()).then(data => {{
                showToast("✅ Location & Job Type preferences saved!");
            }});
        }}

        // CV Management & Viewing
        function renderRoleDropdown() {{
            const sel = document.getElementById("cv-role-select");
            sel.innerHTML = `<option value="default">Default / Fallback CV</option>`;
            currentRoles.forEach(r => {{
                sel.innerHTML += `<option value="${{r}}">${{r}}</option>`;
            }});

            const tbody = document.getElementById("cv-mapping-body");
            tbody.innerHTML = "";
            for (const [role, path] of Object.entries(currentResumes)) {{
                const fname = path.split("/").pop();
                tbody.innerHTML += `
                    <tr>
                        <td><strong>${{role}}</strong></td>
                        <td>📄 ${{fname}}</td>
                        <td>
                            <a href="/resumes/${{fname}}" target="_blank" style="color:var(--accent); font-weight:600; text-decoration:none;">
                                👁️ View / Download PDF ↗
                            </a>
                        </td>
                    </tr>
                `;
            }}
        }}

        function uploadResume() {{
            const fileInput = document.getElementById("cv-file-input");
            const roleSelect = document.getElementById("cv-role-select");
            if (!fileInput.files || fileInput.files.length === 0) {{
                alert("Please select a PDF resume to upload.");
                return;
            }}
            const file = fileInput.files[0];
            const reader = new FileReader();
            reader.onload = function(e) {{
                const b64Data = e.target.result.split(",")[1];
                fetch("/api/upload-cv", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{
                        role: roleSelect.value,
                        filename: file.name,
                        filedata: b64Data
                    }})
                }}).then(res => res.json()).then(data => {{
                    currentResumes[roleSelect.value] = data.saved_path;
                    renderRoleDropdown();
                    showToast("✅ CV successfully uploaded & mapped to " + roleSelect.value);
                }});
            }};
            reader.readAsDataURL(file);
        }}

        function triggerCycle() {{
            const btn = document.getElementById("trigger-btn");
            const indicator = document.getElementById("running-indicator");
            btn.disabled = true;
            indicator.style.display = "inline";
            fetch("/api/trigger-cycle", {{ method: "POST" }})
                .then(res => res.json())
                .then(() => {{
                    showToast("🚀 Search & Apply cycle started in background!");
                    setTimeout(() => {{ window.location.reload(); }}, 10000);
                }});
        }}

        renderRoles();
        renderLocations();
    </script>
</body>
</html>
"""
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    return html

def generate_dashboard() -> str:
    render_dashboard_html()
    return str(DASHBOARD_FILE)

class InteractiveHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/index.html", "/dashboard.html"]:
            html = render_dashboard_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif self.path.startswith("/resumes/"):
            filename = self.path.replace("/resumes/", "").split("?")[0]
            file_path = RESUMES_DIR / filename
            if file_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f"inline; filename={filename}")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(EXECUTION_STATE).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        data = json.loads(body) if body else {}

        if self.path == "/api/roles":
            cfg = load_config()
            cfg.setdefault("search", {})["roles"] = data.get("roles", [])
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "roles": cfg["search"]["roles"]}).encode("utf-8"))

        elif self.path == "/api/search-settings":
            cfg = load_config()
            cfg.setdefault("search", {})["locations"] = data.get("locations", ["Nigeria"])
            cfg["search"]["job_type"] = data.get("job_type", "both")
            save_config(cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))

        elif self.path == "/api/upload-cv":
            import base64
            role = data.get("role", "default")
            raw_filename = data.get("filename", "resume.pdf")
            b64_content = data.get("filedata", "")
            
            RESUMES_DIR.mkdir(parents=True, exist_ok=True)
            safe_filename = "".join(c for c in raw_filename if c.isalnum() or c in (".", "_", "-"))
            save_path = RESUMES_DIR / safe_filename

            with open(save_path, "wb") as f:
                f.write(base64.b64decode(b64_content))

            rel_path = f"resumes/{safe_filename}"
            cfg = load_config()
            cfg.setdefault("resumes", {})[role] = rel_path
            save_config(cfg)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "saved_path": rel_path}).encode("utf-8"))

        elif self.path == "/api/trigger-cycle":
            threading.Thread(target=run_cycle_thread, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

def serve_dashboard(port: int = 8080):
    generate_dashboard()
    with socketserver.TCPServer(("", port), InteractiveHandler) as httpd:
        print(f"\n🌐 Interactive Dashboard live at http://localhost:{port}")
        print("Features enabled: Role Selection, Location & Job Type Settings, CV Upload & Preview, 1-Click Trigger.")
        print("Press Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
