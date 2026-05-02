import logging
import smtplib
from asyncio import to_thread
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings

logger = logging.getLogger(__name__)


class EmailSender:
    async def send_verification_code(self, email: str, code: str) -> None:
        if not settings.smtp_host:
            logger.info("Email verification code for %s: %s", email, code)
            return

        message = self._build_verification_message(email, code)
        await to_thread(self._send_message, message)

    def _build_verification_message(self, email: str, code: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = "Код подтверждения Parser Monitor"
        message["From"] = formataddr((settings.email_from_name, settings.email_from))
        message["To"] = email
        message.set_content(
            "\n".join(
                [
                    "Здравствуйте!",
                    "",
                    f"Ваш код подтверждения: {code}",
                    "",
                    f"Код действует {settings.email_code_ttl_minutes} минут.",
                    "Если вы не запрашивали код, просто проигнорируйте это письмо.",
                ]
            )
        )
        return message

    def _send_message(self, message: EmailMessage) -> None:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
            if not settings.smtp_use_ssl and settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
        logger.info("Verification email sent to %s", message["To"])


email_sender = EmailSender()
