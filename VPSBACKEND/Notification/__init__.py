import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_NAME = os.getenv("FROM_NAME", "VPS Store")


def _send(to: str, subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to, msg.as_string())


async def send_login_email(to_email: str, ip: str, device: str, location: dict):
    now     = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")
    city    = location.get("city", "Unknown")
    region  = location.get("region", "Unknown")
    country = location.get("country", "Unknown")
    isp     = location.get("isp", "Unknown")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">

      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
        <tr>
          <td align="center">
            <table width="600" cellpadding="0" cellspacing="0"
              style="background:#ffffff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">

              <!-- Header -->
              <tr>
                <td style="background:#1a1a2e;padding:28px 32px;">
                  <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">
                    Security Notification
                  </p>
                  <h1 style="margin:8px 0 0;color:#ffffff;font-size:22px;font-weight:600;">
                    New Login Detected
                  </h1>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:32px;">
                  <p style="margin:0 0 24px;font-size:15px;color:#444;line-height:1.6;">
                    A new login was detected on your <strong>VPS Store</strong> account.
                    Please review the details below.
                  </p>

                  <!-- Info Table -->
                  <table width="100%" cellpadding="0" cellspacing="0"
                    style="border:1px solid #e8e8e8;border-radius:4px;overflow:hidden;font-size:14px;">
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;width:35%;border-bottom:1px solid #e8e8e8;">
                        Date &amp; Time
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">
                        {now}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        IP Address
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;font-family:monospace;">
                        {ip}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        Location
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">
                        {city}, {region}, {country}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        ISP
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">
                        {isp}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;">
                        Device
                      </td>
                      <td style="padding:12px 16px;color:#222;">
                        {device}
                      </td>
                    </tr>
                  </table>

                  <!-- Warning Box -->
                  <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                    <tr>
                      <td style="background:#fef9ec;border:1px solid #f0d080;border-left:4px solid #f0a500;
                                 border-radius:4px;padding:16px 20px;">
                        <p style="margin:0;font-size:13px;color:#7a5c00;line-height:1.6;">
                          <strong>Not you?</strong> If you did not perform this login, please change your
                          password immediately and contact our support team.
                        </p>
                      </td>
                    </tr>
                  </table>

                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                  <p style="margin:0;font-size:12px;color:#aaa;line-height:1.6;">
                    This is an automated security alert from <strong>VPS Store</strong>.
                    Please do not reply to this email.
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>

    </body>
    </html>
    """

    _send(to_email, "Security Alert: New Login to Your VPS Store Account", html)

async def send_welcome_email(to_email: str, ip: str, device: str, location: dict):
    from datetime import datetime

    now     = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")
    city    = location.get("city", "Unknown")
    region  = location.get("region", "Unknown")
    country = location.get("country", "Unknown")
    isp     = location.get("isp", "Unknown")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">

      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
        <tr>
          <td align="center">
            <table width="600" cellpadding="0" cellspacing="0"
              style="background:#ffffff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">

              <!-- Header -->
              <tr>
                <td style="background:#1a1a2e;padding:28px 32px;">
                  <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">
                    Welcome to VPS Store
                  </p>
                  <h1 style="margin:8px 0 0;color:#ffffff;font-size:22px;font-weight:600;">
                    Account Successfully Created
                  </h1>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:32px;">
                  <p style="margin:0 0 24px;font-size:15px;color:#444;line-height:1.6;">
                    Your <strong>VPS Store</strong> account has been created.
                    Below are the details of this registration.
                  </p>

                  <!-- Info Table -->
                  <table width="100%" cellpadding="0" cellspacing="0"
                    style="border:1px solid #e8e8e8;border-radius:4px;overflow:hidden;font-size:14px;">
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;width:35%;border-bottom:1px solid #e8e8e8;">
                        Date &amp; Time
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">
                        {now}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        Email
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;font-family:monospace;">
                        {to_email}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        IP Address
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;font-family:monospace;">
                        {ip}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        Location
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">
                        {city}, {region}, {country}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">
                        ISP
                      </td>
                      <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">
                        {isp}
                      </td>
                    </tr>
                    <tr>
                      <td style="padding:12px 16px;background:#f9f9f9;color:#888;">
                        Device
                      </td>
                      <td style="padding:12px 16px;color:#222;">
                        {device}
                      </td>
                    </tr>
                  </table>

                  <!-- Warning Box -->
                  <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                    <tr>
                      <td style="background:#fef9ec;border:1px solid #f0d080;border-left:4px solid #f0a500;
                                 border-radius:4px;padding:16px 20px;">
                        <p style="margin:0;font-size:13px;color:#7a5c00;line-height:1.6;">
                          <strong>Not you?</strong> If you did not create this account, please contact
                          our support team immediately as someone may have used your email address.
                        </p>
                      </td>
                    </tr>
                  </table>

                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                  <p style="margin:0;font-size:12px;color:#aaa;line-height:1.6;">
                    This is an automated notification from <strong>VPS Store</strong>.
                    Please do not reply to this email.
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>

    </body>
    </html>
    """

    _send(to_email, "Welcome to VPS Store — Account Created", html)

async def send_password_changed_email(to_email: str):
    from datetime import datetime
    now = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
        <tr><td align="center">
          <table width="600" cellpadding="0" cellspacing="0"
            style="background:#fff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">
            <tr>
              <td style="background:#1a1a2e;padding:28px 32px;">
                <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">Security Notification</p>
                <h1 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:600;">Password Changed</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <p style="font-size:15px;color:#444;line-height:1.6;">
                  The password for your <strong>VPS Store</strong> account was successfully changed on <strong>{now}</strong>.
                </p>
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                  <tr>
                    <td style="background:#fef9ec;border:1px solid #f0d080;border-left:4px solid #f0a500;
                               border-radius:4px;padding:16px 20px;">
                      <p style="margin:0;font-size:13px;color:#7a5c00;line-height:1.6;">
                        <strong>Not you?</strong> If you did not make this change, please contact support immediately.
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                <p style="margin:0;font-size:12px;color:#aaa;">
                  This is an automated notification from <strong>VPS Store</strong>. Do not reply.
                </p>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """
    _send(to_email, "Security Alert: Your Password Was Changed", html)


async def send_email_changed_email(old_email: str, new_email: str):
    from datetime import datetime
    now = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    for recipient in [old_email, new_email]:
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
            <tr><td align="center">
              <table width="600" cellpadding="0" cellspacing="0"
                style="background:#fff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">
                <tr>
                  <td style="background:#1a1a2e;padding:28px 32px;">
                    <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">Security Notification</p>
                    <h1 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:600;">Email Address Changed</h1>
                  </td>
                </tr>
                <tr>
                  <td style="padding:32px;">
                    <p style="font-size:15px;color:#444;line-height:1.6;">
                      The email address on your <strong>VPS Store</strong> account was changed on <strong>{now}</strong>.
                    </p>
                    <table width="100%" cellpadding="0" cellspacing="0"
                      style="border:1px solid #e8e8e8;border-radius:4px;overflow:hidden;font-size:14px;margin-top:16px;">
                      <tr>
                        <td style="padding:12px 16px;background:#f9f9f9;color:#888;width:35%;border-bottom:1px solid #e8e8e8;">Previous Email</td>
                        <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;font-family:monospace;">{old_email}</td>
                      </tr>
                      <tr>
                        <td style="padding:12px 16px;background:#f9f9f9;color:#888;">New Email</td>
                        <td style="padding:12px 16px;color:#222;font-family:monospace;">{new_email}</td>
                      </tr>
                    </table>
                    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                      <tr>
                        <td style="background:#fef9ec;border:1px solid #f0d080;border-left:4px solid #f0a500;
                                   border-radius:4px;padding:16px 20px;">
                          <p style="margin:0;font-size:13px;color:#7a5c00;line-height:1.6;">
                            <strong>Not you?</strong> Contact support immediately to secure your account.
                          </p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                    <p style="margin:0;font-size:12px;color:#aaa;">
                      This is an automated notification from <strong>VPS Store</strong>. Do not reply.
                    </p>
                  </td>
                </tr>
              </table>
            </td></tr>
          </table>
        </body>
        </html>
        """
        _send(recipient, "Security Alert: Email Address Changed on Your Account", html)


async def send_account_deleted_email(to_email: str):
    from datetime import datetime
    now = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
        <tr><td align="center">
          <table width="600" cellpadding="0" cellspacing="0"
            style="background:#fff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">
            <tr>
              <td style="background:#1a1a2e;padding:28px 32px;">
                <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">Account Notice</p>
                <h1 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:600;">Account Deleted</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <p style="font-size:15px;color:#444;line-height:1.6;">
                  Your <strong>VPS Store</strong> account associated with
                  <span style="font-family:monospace;">{to_email}</span>
                  was permanently deleted on <strong>{now}</strong>.
                </p>
                <p style="font-size:14px;color:#666;line-height:1.6;">
                  All associated data has been removed from our systems.
                  If you wish to use our services again, you may create a new account.
                </p>
                <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
                  <tr>
                    <td style="background:#fef9ec;border:1px solid #f0d080;border-left:4px solid #f0a500;
                               border-radius:4px;padding:16px 20px;">
                      <p style="margin:0;font-size:13px;color:#7a5c00;line-height:1.6;">
                        <strong>Not you?</strong> If you did not request this deletion, contact support immediately.
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                <p style="margin:0;font-size:12px;color:#aaa;">
                  This is an automated notification from <strong>VPS Store</strong>. Do not reply.
                </p>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """
    _send(to_email, "Your VPS Store Account Has Been Deleted", html)

async def send_vps_created_email(
    to_email: str, server_name: str, ip: str,
    instance_type: str, os_name: str, expires_at: str
):
    from datetime import datetime
    now = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
        <tr><td align="center">
          <table width="600" cellpadding="0" cellspacing="0"
            style="background:#fff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">
            <tr>
              <td style="background:#1a1a2e;padding:28px 32px;">
                <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">
                  VPS Notification
                </p>
                <h1 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:600;">
                  Your VPS is Ready
                </h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <p style="font-size:15px;color:#444;line-height:1.6;">
                  Your VPS server has been created and is ready to use.
                </p>
                <table width="100%" cellpadding="0" cellspacing="0"
                  style="border:1px solid #e8e8e8;border-radius:4px;overflow:hidden;font-size:14px;margin-top:16px;">
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;width:35%;border-bottom:1px solid #e8e8e8;">Server Name</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{server_name}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">IP Address</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;font-family:monospace;">{ip}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">Instance Type</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{instance_type}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">Operating System</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{os_name}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">Created At</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{now}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;">Expires At</td>
                    <td style="padding:12px 16px;color:#222;">{expires_at}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                <p style="margin:0;font-size:12px;color:#aaa;">
                  This is an automated notification from <strong>VPS Store</strong>. Do not reply.
                </p>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """
    _send(to_email, "Your VPS Server is Ready — VPS Store", html)

# ─────────────────────────────────────────
# Sync Wrappers (Celery tasks ke liye)
# asyncio.run() Celery mein crash karta hai
# isliye yeh sync versions use karo
# ─────────────────────────────────────────

def send_vps_created_email_sync(
    to_email: str, server_name: str, ip: str,
    instance_type: str, os_name: str, expires_at: str
):
    """Celery task se call karo — async nahi."""
    from datetime import datetime
    now = datetime.utcnow().strftime("%d %B %Y, %I:%M %p UTC")

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:40px 0;">
        <tr><td align="center">
          <table width="600" cellpadding="0" cellspacing="0"
            style="background:#fff;border-radius:6px;overflow:hidden;border:1px solid #ddd;">
            <tr>
              <td style="background:#1a1a2e;padding:28px 32px;">
                <p style="margin:0;font-size:11px;color:#8888aa;letter-spacing:2px;text-transform:uppercase;">
                  VPS Notification
                </p>
                <h1 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:600;">
                  Your VPS is Ready
                </h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <p style="font-size:15px;color:#444;line-height:1.6;">
                  Your VPS server has been created and is ready to use.
                </p>
                <table width="100%" cellpadding="0" cellspacing="0"
                  style="border:1px solid #e8e8e8;border-radius:4px;overflow:hidden;font-size:14px;margin-top:16px;">
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;width:35%;border-bottom:1px solid #e8e8e8;">Server Name</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{server_name}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">IP Address</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;font-family:monospace;">{ip}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">Instance Type</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{instance_type}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">Operating System</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{os_name}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;border-bottom:1px solid #e8e8e8;">Created At</td>
                    <td style="padding:12px 16px;color:#222;border-bottom:1px solid #e8e8e8;">{now}</td>
                  </tr>
                  <tr>
                    <td style="padding:12px 16px;background:#f9f9f9;color:#888;">Expires At</td>
                    <td style="padding:12px 16px;color:#222;">{expires_at}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="background:#f4f4f4;padding:20px 32px;border-top:1px solid #e8e8e8;">
                <p style="margin:0;font-size:12px;color:#aaa;">
                  This is an automated notification from <strong>VPS Store</strong>. Do not reply.
                </p>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """
    _send(to_email, "Your VPS Server is Ready — VPS Store", html)
    
