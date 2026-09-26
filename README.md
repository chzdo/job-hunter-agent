# 🤖 Job Hunter & Auto-Apply Scheduler

An automated agent that periodically searches for target job postings across **all major platforms** (LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Google Jobs), matches them against your candidate profile, and automates/queues applications on your behalf.

---

## 🎯 Configured Target Roles
* **Software Testing / QA Engineer**
* **Product Management / Product Manager**
* **Personal Assistant (PA)**
* **Customer Care / Support Representative**

## 🌐 Supported Platforms
* **LinkedIn**
* **Indeed**
* **Glassdoor**
* **ZipRecruiter**
* **Google Jobs**

---

## 🚀 Quick Start

### 1. Configure Your Candidate Profile & Resume
Open `config.yaml` and update your details:
```yaml
candidate:
  full_name: "Your Full Name"
  email: "your.email@example.com"
  phone: "+1234567890"
  resume_path: "resumes/resume.pdf" # Place your PDF resume in resumes/

screening_answers:
  authorized_to_work: "Yes"
  require_sponsorship: "No"
  years_of_experience:
    "software testing": 4
    "product management": 3
    "personal assistant": 3
    "customer care": 4
    "default": 3
```

Place your resume inside the `resumes/` folder:
```bash
cp /path/to/your/resume.pdf /Users/macbookpro/Downloads/atb/HR/job-hunter-agent/resumes/resume.pdf
```

---

## 💻 Commands

From the `job-hunter-agent` directory:

```bash
cd /Users/macbookpro/Downloads/atb/HR/job-hunter-agent
source venv/bin/activate
```

### 1. Dry Run (Search without applying)
Test searches across all platforms, parses results, and stores matching jobs in SQLite without submitting:
```bash
python cli.py --dry-run
```

### 2. View Database Statistics & Stored Jobs
```bash
# View summary table (Discovered, Queued, Applied, Failed)
python cli.py --stats

# List discovered or queued jobs
python cli.py --list DISCOVERED
python cli.py --list QUEUED
```

### 3. Immediate Run (Single Search + Apply Cycle)
```bash
python cli.py --run-cycle
```

### 4. Start 12-Hour Scheduler
Runs an immediate cycle and then automatically triggers every 12 hours:
```bash
python cli.py --start
```

### 5. Run in Background (Daemon Mode)
To keep the scheduler running permanently in the background:
```bash
nohup python cli.py --start > scheduler.log 2>&1 &
```

---

## 🛡️ Anti-Bot Safety & Terms Considerations
* **Realistic Delays**: Playwright introduces randomized human-like delays (1.5s - 3.5s) between interactions.
* **Daily Caps**: Enforces a configurable cap (default 20 applications/cycle) to prevent account bans or rate limits.
* **Persistent Session**: Browser cookies are stored in `data/browser_profile` to stay logged in without repeated 2FA challenges.
* **Deduplication**: Every listing is indexed in SQLite (`data/jobs.db`) so you never apply to or process the same posting twice.
