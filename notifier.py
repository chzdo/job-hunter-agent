import os
import smtplib
import logging
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger("job_hunter.notifier")

def send_email_report(config: Dict[str, Any], stats: Dict[str, Any], recent_jobs: List[Dict[str, Any]]) -> bool:
    """
    Send an email summary report of the latest job cycle using a free email service
    (Gmail SMTP, Brevo SMTP, or Resend API).
    """
    email_cfg = config.get("email_notifications", {})
    if not email_cfg.get("enabled", True):
        logger.info("Email notifications are disabled in configuration.")
        return False

    recipient = email_cfg.get("recipient_email") or os.getenv("EMAIL_RECIPIENT", "")
    if not recipient:
        logger.warning("No recipient email specified for notifications.")
        return False

    service = email_cfg.get("service", "smtp").lower()
    subject = f"🤖 Job Hunter Cycle Report - {stats.get('APPLIED', 0)} Applied, {stats.get('DISCOVERED', 0)} Discovered ({datetime.now().strftime('%b %d, %H:%M')})"

    # Generate HTML content
    job_rows = ""
    for j in recent_jobs[:15]:
        status_color = "#10b981" if j.get("status") == "APPLIED" else "#f59e0b" if j.get("status") == "QUEUED" else "#38bdf8"
        job_rows += f"""
        <tr>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">
                <span style="background-color: {status_color}; color: #fff; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">
                    {j.get('status', 'DISCOVERED')}
                </span>
            </td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-weight: bold;">{j.get('title', 'N/A')}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{j.get('company', 'N/A')}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{j.get('location', 'N/A')}</td>
            <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">
                <a href="{j.get('job_url', '#')}" style="color: #2563eb; text-decoration: none;">View Job ↗</a>
            </td>
        </tr>
        """

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px;">
        <div style="max-width: 650px; margin: auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden;">
            <div style="background-color: #0f172a; color: #ffffff; padding: 20px;">
                <h2 style="margin: 0; font-size: 20px;">🤖 Job Hunter Agent Report</h2>
                <p style="margin: 5px 0 0 0; color: #94a3b8; font-size: 13px;">Cycle completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div style="padding: 20px;">
                <h3 style="margin-top: 0;">Cycle Summary</h3>
                <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                    <div style="background: #f1f5f9; padding: 12px; border-radius: 6px; text-align: center; flex: 1;">
                        <div style="font-size: 11px; color: #64748b; text-transform: uppercase;">Discovered</div>
                        <div style="font-size: 22px; font-weight: bold; color: #0284c7;">{stats.get('DISCOVERED', 0)}</div>
                    </div>
                    <div style="background: #f1f5f9; padding: 12px; border-radius: 6px; text-align: center; flex: 1;">
                        <div style="font-size: 11px; color: #64748b; text-transform: uppercase;">Applied</div>
                        <div style="font-size: 22px; font-weight: bold; color: #10b981;">{stats.get('APPLIED', 0)}</div>
                    </div>
                    <div style="background: #f1f5f9; padding: 12px; border-radius: 6px; text-align: center; flex: 1;">
                        <div style="font-size: 11px; color: #64748b; text-transform: uppercase;">Queued / Review</div>
                        <div style="font-size: 22px; font-weight: bold; color: #f59e0b;">{stats.get('QUEUED', 0)}</div>
                    </div>
                </div>

                <h3>Latest Opportunities</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                    <thead>
                        <tr style="background: #f8fafc; color: #64748b;">
                            <th style="padding: 8px 12px;">Status</th>
                            <th style="padding: 8px 12px;">Role</th>
                            <th style="padding: 8px 12px;">Company</th>
                            <th style="padding: 8px 12px;">Location</th>
                            <th style="padding: 8px 12px;">Link</th>
                        </tr>
                    </thead>
                    <tbody>
                        {job_rows if job_rows else "<tr><td colspan='5' style='padding: 12px; text-align: center;'>No new jobs in this run.</td></tr>"}
                    </tbody>
                </table>
            </div>
            
            <div style="background: #f8fafc; padding: 15px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
                Sent by your Autonomous Job Hunter Agent • Runs every 12 hours
            </div>
        </div>
    </body>
    </html>
    """

    # 1. Option A: Free Resend API (if RESEND_API_KEY is present)
    resend_key = os.getenv("RESEND_API_KEY", "")
    if service == "resend" or resend_key:
        try:
            logger.info(f"Sending notification email via Resend API to {recipient}...")
            res = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "Job Hunter <onboarding@resend.dev>",
                    "to": [recipient],
                    "subject": subject,
                    "html": html_body
                },
                timeout=10
            )
            if res.status_code in [200, 201]:
                logger.info("Email sent successfully via Resend!")
                return True
            else:
                logger.warning(f"Resend API returned status {res.status_code}: {res.text}. Falling back to SMTP...")
        except Exception as e:
            logger.error(f"Error using Resend API: {e}. Falling back to SMTP...")

    # 2. Option B: Free SMTP (Gmail, Brevo, Outlook, etc.)
    sender = os.getenv("EMAIL_SENDER") or email_cfg.get("sender_email")
    password = os.getenv("EMAIL_PASSWORD") or email_cfg.get("sender_password")
    smtp_server = email_cfg.get("smtp_server", "smtp.gmail.com")
    smtp_port = email_cfg.get("smtp_port", 587)

    if not sender or not password:
        logger.warning("EMAIL_SENDER or EMAIL_PASSWORD not provided in .env/config; skipping email send.")
        return False

    try:
        logger.info(f"Connecting to SMTP server {smtp_server}:{smtp_port} as {sender}...")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

        logger.info(f"Email report successfully delivered to {recipient}!")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")
        return False
