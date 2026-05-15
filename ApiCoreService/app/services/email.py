import logging

from app.config import settings
from app.services.rabbitmq import rabbitmq

logger = logging.getLogger(__name__)


class EmailSender:
    async def send_verification_code(self, email: str, code: str) -> None:
        if not rabbitmq.notification_exchange:
            logger.warning(
                "RabbitMQ not connected — verification code for %s will not be delivered via email. "
                "Use dev_code from the API response for testing.",
                email,
            )
            return
        await rabbitmq.publish_verification_code(email, code, settings.email_code_ttl_minutes)


email_sender = EmailSender()
