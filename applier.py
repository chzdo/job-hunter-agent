import os
import time
import random
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext

from matcher import resolve_screening_question
from database import update_job_status

load_dotenv()
logger = logging.getLogger("job_hunter.applier")

def human_delay(min_sec: float = 1.0, max_sec: float = 2.5):
    """Wait for a random human-like duration."""
    time.sleep(random.uniform(min_sec, max_sec))

class PlaywrightApplier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.candidate = config.get("candidate", {})
        self.browser_cfg = config.get("browser", {})
        self.resume_path = Path(self.candidate.get("resume_path", "resumes/resume.pdf")).resolve()
        self.headless = self.browser_cfg.get("headless", True)  # Headless by default for background execution
        self.user_data_dir = Path(__file__).parent / "data" / "browser_profile"
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self.linkedin_email = os.getenv("LINKEDIN_EMAIL", "")
        self.linkedin_password = os.getenv("LINKEDIN_PASSWORD", "")
        self.indeed_email = os.getenv("INDEED_EMAIL", "")
        self.indeed_password = os.getenv("INDEED_PASSWORD", "")

    def ensure_authenticated(self, page: Page, site: str) -> bool:
        """
        Verify if the browser is logged in. If not, auto-fill credentials without human intervention.
        """
        if "linkedin" in site.lower():
            return self._ensure_linkedin_login(page)
        elif "indeed" in site.lower():
            return self._ensure_indeed_login(page)
        return True

    def _ensure_linkedin_login(self, page: Page) -> bool:
        """Check login status and auto-login to LinkedIn if credentials are provided."""
        page.goto("https://www.linkedin.com/feed/", timeout=30000)
        human_delay(1.5, 2.5)

        # If already on feed, we are logged in
        if "feed" in page.url:
            return True

        if not self.linkedin_email or not self.linkedin_password:
            logger.warning("LinkedIn credentials not set in .env; skipping automated login.")
            return False

        logger.info("Attempting automated LinkedIn credential login...")
        page.goto("https://www.linkedin.com/login", timeout=30000)
        human_delay(1, 2)

        try:
            email_field = page.query_selector("#username")
            pwd_field = page.query_selector("#password")
            submit_btn = page.query_selector("button[type='submit']")

            if email_field and pwd_field and submit_btn:
                email_field.fill(self.linkedin_email)
                human_delay(0.5, 1.0)
                pwd_field.fill(self.linkedin_password)
                human_delay(0.5, 1.0)
                submit_btn.click()
                human_delay(3, 5)

                if "feed" in page.url:
                    logger.info("Automated LinkedIn login successful!")
                    return True

                # Check if security challenge/CAPTCHA blocked login
                if "challenge" in page.url or page.query_selector("#captcha-internal"):
                    logger.error("LinkedIn security challenge/CAPTCHA detected. Automated login blocked.")
                    return False
        except Exception as e:
            logger.error(f"Failed during automated LinkedIn login: {e}")

        return "feed" in page.url

    def _ensure_indeed_login(self, page: Page) -> bool:
        """Check login status and auto-login to Indeed if credentials exist."""
        page.goto("https://myjobs.indeed.com/", timeout=30000)
        human_delay(1.5, 2.5)
        if "auth" not in page.url and "login" not in page.url:
            return True

        if not self.indeed_email or not self.indeed_password:
            return False

        try:
            page.goto("https://secure.indeed.com/auth", timeout=30000)
            human_delay(1, 2)
            email_field = page.query_selector("input[type='email']")
            if email_field:
                email_field.fill(self.indeed_email)
                page.keyboard.press("Enter")
                human_delay(2, 3)

            pwd_field = page.query_selector("input[type='password']")
            if pwd_field:
                pwd_field.fill(self.indeed_password)
                page.keyboard.press("Enter")
                human_delay(3, 5)
        except Exception as e:
            logger.error(f"Failed during automated Indeed login: {e}")

        return "auth" not in page.url

    def apply_to_job(self, job: Dict[str, Any]) -> bool:
        """
        Fully automated application without any human intervention.
        """
        site = job.get("site", "").lower()
        job_url = job.get("job_url", "")
        job_id = job.get("id", "")

        if not job_url:
            update_job_status(job_id, "FAILED", "Missing job URL")
            return False

        logger.info(f"Processing application: {job.get('title')} at {job.get('company')} ({site})")

        with sync_playwright() as p:
            context: BrowserContext = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page: Page = context.new_page()

            try:
                # Ensure session is authenticated if credentials exist
                self.ensure_authenticated(page, site)

                # Navigate directly to the job listing
                page.goto(job_url, timeout=40000)
                human_delay(2, 3)

                if "linkedin" in site:
                    success = self._apply_linkedin_easy_apply(page, job)
                elif any(ats in job_url for ats in ["greenhouse.io", "lever.co", "ashbyhq.com"]):
                    success = self._apply_ats_form(page, job)
                else:
                    logger.info(f"External job board redirect: {job_url}. Marking QUEUED.")
                    update_job_status(job_id, "QUEUED", "External application link")
                    context.close()
                    return False

                if success:
                    update_job_status(job_id, "APPLIED")
                    logger.info(f"Applied successfully to {job.get('title')} at {job.get('company')}")
                else:
                    update_job_status(job_id, "SKIPPED", "Easy Apply not available or form required complex custom fields")

                context.close()
                return success

            except Exception as e:
                logger.error(f"Error applying to job {job_id}: {e}")
                update_job_status(job_id, "FAILED", str(e))
                context.close()
                return False

    def _apply_linkedin_easy_apply(self, page: Page, job: Dict[str, Any]) -> bool:
        """Fully automated LinkedIn Easy Apply without human prompts."""
        easy_apply_btn = page.query_selector("button.jobs-apply-button")
        if not easy_apply_btn:
            # Fallback selectors
            easy_apply_btn = page.query_selector(".jobs-apply-button--top-card button")

        if not easy_apply_btn or "easy apply" not in easy_apply_btn.inner_text().lower():
            return False

        easy_apply_btn.click()
        human_delay(1.5, 2.5)

        max_steps = 7
        step = 0

        while step < max_steps:
            step += 1
            human_delay(1.0, 2.0)

            # Auto-upload resume if file upload input is present
            file_input = page.query_selector("input[type='file']")
            if file_input and self.resume_path.exists():
                try:
                    file_input.set_input_files(str(self.resume_path))
                    human_delay(1.0, 1.5)
                except Exception:
                    pass

            # Auto-fill inputs & screening questions
            form_inputs = page.query_selector_all("input[type='text'], input[type='number'], textarea")
            for inp in form_inputs:
                try:
                    val = inp.input_value()
                    if not val:
                        label_elem = page.query_selector(f"label[for='{inp.get_attribute('id')}']")
                        label_text = label_elem.inner_text() if label_elem else ""
                        ans = resolve_screening_question(label_text, self.config, job.get("title", ""))
                        if ans:
                            inp.fill(ans)
                            human_delay(0.3, 0.6)
                except Exception:
                    pass

            # Handle radio buttons (e.g. Authorized to work -> Yes, Need sponsorship -> No)
            radios = page.query_selector_all("input[type='radio']")
            for r in radios:
                try:
                    label_text = r.evaluate("el => el.closest('fieldset')?.innerText || ''").lower()
                    if "authorized" in label_text and "yes" in r.get_attribute("value", "").lower():
                        r.check()
                    elif "sponsorship" in label_text and "no" in r.get_attribute("value", "").lower():
                        r.check()
                except Exception:
                    pass

            # Check for submit button
            submit_btn = page.query_selector("button[aria-label='Submit application']")
            if submit_btn:
                submit_btn.click()
                human_delay(2.0, 3.0)
                # Close confirmation modal if present
                dismiss = page.query_selector("button[aria-label='Dismiss']")
                if dismiss:
                    dismiss.click()
                return True

            # Check next or review buttons
            review_btn = page.query_selector("button[aria-label='Review your application']")
            if review_btn:
                review_btn.click()
                human_delay(1.0, 2.0)
                continue

            next_btn = page.query_selector("button[aria-label='Continue to next step']") or page.query_selector("button[data-easy-apply-next-button]")
            if next_btn:
                next_btn.click()
                human_delay(1.0, 2.0)
                continue

            break

        return False

    def _apply_ats_form(self, page: Page, job: Dict[str, Any]) -> bool:
        """Auto-fill and submit Greenhouse / Lever / Ashby forms automatically."""
        candidate = self.candidate
        field_mappings = {
            "first_name": candidate.get("full_name", "").split()[0] if candidate.get("full_name") else "",
            "last_name": " ".join(candidate.get("full_name", "").split()[1:]) if candidate.get("full_name") else "",
            "name": candidate.get("full_name", ""),
            "email": candidate.get("email", ""),
            "phone": candidate.get("phone", ""),
            "linkedin": candidate.get("linkedin_url", ""),
            "github": candidate.get("github_url", ""),
            "portfolio": candidate.get("portfolio_url", "")
        }

        for field, value in field_mappings.items():
            if not value:
                continue
            selector = f"input[name*='{field}' i], input[id*='{field}' i]"
            el = page.query_selector(selector)
            if el and not el.input_value():
                try:
                    el.fill(value)
                    human_delay(0.3, 0.6)
                except Exception:
                    pass

        # Attach resume
        file_input = page.query_selector("input[type='file']")
        if file_input and self.resume_path.exists():
            try:
                file_input.set_input_files(str(self.resume_path))
                human_delay(1.0, 1.5)
            except Exception:
                pass

        # Attempt submission on ATS
        submit_btn = page.query_selector("button[type='submit'], input[type='submit']")
        if submit_btn:
            try:
                submit_btn.click()
                human_delay(2.0, 3.0)
                return True
            except Exception:
                pass

        return False
