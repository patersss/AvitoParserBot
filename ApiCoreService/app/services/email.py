import logging

logger = logging.getLogger(__name__)


class EmailSender:
    async def send_verification_code(self, email: str, code: str) -> None:
        logger.info("Email verification code for %s: %s", email, code)


email_sender = EmailSender()
