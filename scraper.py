import logging
from typing import List, Dict, Any
import pandas as pd
from jobspy import scrape_jobs
from database import save_job, job_exists

logger = logging.getLogger("job_hunter.scraper")

def run_job_search(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search for jobs across all configured roles and platforms.
    Deduplicates results against SQLite database.
    """
    search_cfg = config.get("search", {})
    roles = search_cfg.get("roles", ["Software Testing", "Product Management"])
    platforms = search_cfg.get("platforms", ["linkedin", "indeed", "glassdoor", "zip_recruiter", "google"])
    locations = search_cfg.get("locations", ["Remote"])
    results_wanted = search_cfg.get("results_per_role", 10)
    hours_old = search_cfg.get("hours_old", 72)
    is_remote = search_cfg.get("is_remote", True)

    new_jobs: List[Dict[str, Any]] = []

    for role in roles:
        for loc in locations:
            logger.info(f"🔎 Searching for '{role}' in '{loc}' on {platforms}...")
            try:
                jobs_df: pd.DataFrame = scrape_jobs(
                    site_name=platforms,
                    search_term=role,
                    location=loc,
                    results_wanted=results_wanted,
                    hours_old=hours_old,
                    is_remote=is_remote
                )

                if jobs_df is None or jobs_df.empty:
                    logger.info(f"No results found for '{role}' in '{loc}'.")
                    continue

                logger.info(f"Fetched {len(jobs_df)} raw listings for '{role}'.")

                for _, row in jobs_df.iterrows():
                    # Generate stable unique ID if missing
                    job_id = str(row.get("id")) if pd.notna(row.get("id")) and row.get("id") else f"{row.get('site')}_{hash(str(row.get('job_url')))}"
                    
                    if job_exists(job_id):
                        continue

                    job_record = {
                        "id": job_id,
                        "site": str(row.get("site", "")),
                        "title": str(row.get("title", "")),
                        "company": str(row.get("company", "")),
                        "location": str(row.get("location", "")),
                        "job_url": str(row.get("job_url", "")),
                        "job_type": str(row.get("job_type", "")),
                        "date_posted": str(row.get("date_posted", "")),
                        "is_remote": bool(row.get("is_remote", False)),
                        "description": str(row.get("description", "")),
                        "status": "DISCOVERED"
                    }

                    if save_job(job_record):
                        new_jobs.append(job_record)

            except Exception as e:
                logger.error(f"Error searching for '{role}' in '{loc}': {e}", exc_info=True)

    logger.info(f"✨ Search complete. Total new unique jobs saved to database: {len(new_jobs)}")
    return new_jobs
