import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize database tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                site TEXT,
                title TEXT,
                company TEXT,
                location TEXT,
                job_url TEXT,
                job_type TEXT,
                date_posted TEXT,
                is_remote BOOLEAN,
                description TEXT,
                status TEXT DEFAULT 'DISCOVERED', -- DISCOVERED, QUEUED, APPLIED, SKIPPED, FAILED
                applied_at TEXT,
                error_message TEXT,
                match_score REAL,
                created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                action TEXT,
                details TEXT,
                timestamp TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs (id)
            )
        """)
        conn.commit()

def job_exists(job_id: str, db_path: Path = DB_PATH) -> bool:
    """Check if a job has already been discovered or processed."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,))
        return cursor.fetchone() is not None

def save_job(job: Dict[str, Any], db_path: Path = DB_PATH) -> bool:
    """Save a job if not already present. Returns True if inserted, False if duplicate."""
    if job_exists(job["id"], db_path):
        return False

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (
                id, site, title, company, location, job_url, job_type,
                date_posted, is_remote, description, status, match_score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job["id"],
            job.get("site", ""),
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("job_url", ""),
            job.get("job_type", ""),
            str(job.get("date_posted", "")),
            bool(job.get("is_remote", False)),
            job.get("description", ""),
            job.get("status", "DISCOVERED"),
            job.get("match_score", 0.0),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
    return True

def update_job_status(job_id: str, status: str, error_message: Optional[str] = None, db_path: Path = DB_PATH) -> None:
    """Update job status and log timestamp if applied."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        applied_at = datetime.utcnow().isoformat() if status == "APPLIED" else None
        cursor.execute("""
            UPDATE jobs
            SET status = ?, error_message = ?, applied_at = COALESCE(?, applied_at)
            WHERE id = ?
        """, (status, error_message, applied_at, job_id))
        
        cursor.execute("""
            INSERT INTO application_logs (job_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
        """, (job_id, status, error_message or "", datetime.utcnow().isoformat()))
        conn.commit()

def get_jobs_by_status(status: str, limit: int = 50, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve jobs with a specific status."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit))
        return [dict(row) for row in cursor.fetchall()]

def get_stats(db_path: Path = DB_PATH) -> Dict[str, int]:
    """Get count of jobs by status."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, count(*) FROM jobs GROUP BY status")
        stats = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT count(*) FROM jobs")
        stats["TOTAL"] = cursor.fetchone()[0]
        return stats
