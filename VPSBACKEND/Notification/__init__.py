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
