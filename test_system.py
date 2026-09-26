import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from database import init_db, get_stats, get_jobs_by_status
from scraper import run_job_search
from scheduler import load_config
from notifier import send_email_report
from applier import PlaywrightApplier

def test_scraper():
    print("\n🔍 --- Testing Scraper Engine ---")
    config = load_config()
    # Temporary quick test with 1 job result
    config["search"]["results_per_role"] = 1
    config["search"]["roles"] = ["Software Testing"]
    config["search"]["locations"] = ["Nigeria"]
    print(f"Searching for roles: {config['search']['roles']} in {config['search']['locations']}...")
    jobs = run_job_search(config)
    print(f"✅ Scraper Test Succeeded! Found {len(jobs)} jobs.")
    for j in jobs[:2]:
        print(f"  • [{j.get('site')}] {j.get('title')} at {j.get('company')} ({j.get('location')})")

def test_email():
    print("\n✉️ --- Testing Free Email Notification Service ---")
    config = load_config()
    stats = get_stats()
    recent = get_jobs_by_status("DISCOVERED", limit=5)
    print(f"Sending test email report to: {config.get('email_notifications', {}).get('recipient_email')}...")
    success = send_email_report(config, stats, recent)
    if success:
        print("✅ Email Test Succeeded! Check your inbox.")
    else:
        print("⚠️ Email Test: Could not send. Make sure EMAIL_SENDER and EMAIL_PASSWORD (or RESEND_API_KEY) are set in your .env file.")

def test_browser():
    print("\n🌐 --- Testing Playwright Headless Browser Engine ---")
    config = load_config()
    applier = PlaywrightApplier(config)
    print("Launching Chromium browser context...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.google.com")
            title = page.title()
            browser.close()
            print(f"✅ Browser Test Succeeded! Title: {title}")
    except Exception as e:
        print(f"❌ Browser Test Failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Job Hunter Modules")
    parser.add_argument("--test-scraper", action="store_true", help="Test scraping from LinkedIn/Indeed")
    parser.add_argument("--test-email", action="store_true", help="Send a test notification email")
    parser.add_argument("--test-browser", action="store_true", help="Test Playwright browser launch")
    parser.add_argument("--test-all", action="store_true", help="Run all diagnostic tests")

    args = parser.parse_args()
    init_db()

    if args.test_scraper:
        test_scraper()
    elif args.test_email:
        test_email()
    elif args.test_browser:
        test_browser()
    elif args.test_all:
        test_browser()
        test_scraper()
        test_email()
    else:
        parser.print_help()
