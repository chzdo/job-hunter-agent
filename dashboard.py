import http.server
import socketserver
import threading
from pathlib import Path
from datetime import datetime
from database import get_stats, get_jobs_by_status

DASHBOARD_FILE = Path(__file__).parent / "data" / "dashboard.html"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Hunter Agent - Live Dashboard</title>
    <meta http-equiv="refresh" content="60">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --border: #334155;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #6366f1;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: var(--bg); color: var(--text-primary); padding: 2rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }
        .header h1 { font-size: 1.8rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem; }
        .timestamp { color: var(--text-secondary); font-size: 0.9rem; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.2rem; margin-bottom: 2.5rem; }
        .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .card-title { color: var(--text-secondary); font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
        .card-value { font-size: 2.2rem; font-weight: 700; margin-top: 0.5rem; }
        .card.applied .card-value { color: var(--success); }
        .card.discovered .card-value { color: var(--accent); }
        .card.queued .card-value { color: var(--warning); }
        .card.skipped .card-value { color: var(--info); }
        .card.failed .card-value { color: var(--danger); }
        
        .section-title { font-size: 1.3rem; font-weight: 600; margin-bottom: 1rem; }
        .table-container { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.95rem; }
        th { background: #111827; padding: 1rem; color: var(--text-secondary); font-weight: 600; border-bottom: 1px solid var(--border); }
        td { padding: 1rem; border-bottom: 1px solid var(--border); }
        tr:hover { background: rgba(255, 255, 255, 0.02); }
        
        .badge { display: inline-block; padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
        .badge-applied { background: rgba(16, 185, 129, 0.2); color: var(--success); }
        .badge-discovered { background: rgba(56, 189, 248, 0.2); color: var(--accent); }
        .badge-queued { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge-skipped { background: rgba(99, 102, 241, 0.2); color: var(--info); }
        .badge-failed { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        
        a.job-link { color: var(--accent); text-decoration: none; font-weight: 500; }
        a.job-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>🤖 Job Hunter & Application Agent</h1>
            <div class="timestamp">Live Dashboard • Refreshes automatically every 60s</div>
        </div>
        <div class="timestamp">Last Updated: {{LAST_UPDATED}}</div>
    </div>

    <div class="stats-grid">
        <div class="card discovered">
            <div class="card-title">Total Discovered</div>
            <div class="card-value">{{TOTAL_DISCOVERED}}</div>
        </div>
        <div class="card applied">
            <div class="card-title">Successfully Applied</div>
            <div class="card-value">{{TOTAL_APPLIED}}</div>
        </div>
        <div class="card queued">
            <div class="card-title">Queued / Review</div>
            <div class="card-value">{{TOTAL_QUEUED}}</div>
        </div>
        <div class="card skipped">
            <div class="card-title">Skipped</div>
            <div class="card-value">{{TOTAL_SKIPPED}}</div>
        </div>
        <div class="card failed">
            <div class="card-title">Failed / Blocked</div>
            <div class="card-value">{{TOTAL_FAILED}}</div>
        </div>
    </div>

    <div class="section-title">📋 Recent Applications & Discovered Opportunities</div>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Platform</th>
                    <th>Job Title</th>
                    <th>Company</th>
                    <th>Location</th>
                    <th>Link</th>
                </tr>
            </thead>
            <tbody>
                {{TABLE_ROWS}}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

def generate_dashboard() -> str:
    """Generate the static HTML dashboard file from current SQLite database data."""
    stats = get_stats()
    jobs = []
    for s in ["APPLIED", "QUEUED", "DISCOVERED", "SKIPPED", "FAILED"]:
        jobs.extend(get_jobs_by_status(s, limit=20))

    # Sort by created_at / applied_at
    jobs.sort(key=lambda j: j.get("applied_at") or j.get("created_at") or "", reverse=True)

    rows = []
    for j in jobs[:60]:
        status = j.get("status", "DISCOVERED")
        badge_class = f"badge-{status.lower()}"
        row = f"""
        <tr>
            <td><span class="badge {badge_class}">{status}</span></td>
            <td><strong>{j.get('site', 'N/A').capitalize()}</strong></td>
            <td>{j.get('title', 'N/A')}</td>
            <td>{j.get('company', 'N/A')}</td>
            <td>{j.get('location', 'N/A')}</td>
            <td><a class="job-link" href="{j.get('job_url', '#')}" target="_blank">View Listing ↗</a></td>
        </tr>
        """
        rows.append(row)

    html = HTML_TEMPLATE
    html = html.replace("{{LAST_UPDATED}}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    html = html.replace("{{TOTAL_DISCOVERED}}", str(stats.get("DISCOVERED", 0) + stats.get("TOTAL", 0)))
    html = html.replace("{{TOTAL_APPLIED}}", str(stats.get("APPLIED", 0)))
    html = html.replace("{{TOTAL_QUEUED}}", str(stats.get("QUEUED", 0)))
    html = html.replace("{{TOTAL_SKIPPED}}", str(stats.get("SKIPPED", 0)))
    html = html.replace("{{TOTAL_FAILED}}", str(stats.get("FAILED", 0)))
    html = html.replace("{{TABLE_ROWS}}", "\n".join(rows) if rows else "<tr><td colspan='6' style='text-align:center;'>No jobs recorded yet.</td></tr>")

    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    return str(DASHBOARD_FILE)

def serve_dashboard(port: int = 8080):
    """Serve the dashboard file on a local HTTP server."""
    generate_dashboard()
    web_dir = str(DASHBOARD_FILE.parent)
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)

        def do_GET(self):
            # Always regenerate before serving
            generate_dashboard()
            if self.path in ["/", "/index.html"]:
                self.path = "/dashboard.html"
            return super().do_GET()

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"\n🌐 Dashboard live at http://localhost:{port}")
        print("Press Ctrl+C to stop the dashboard server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
