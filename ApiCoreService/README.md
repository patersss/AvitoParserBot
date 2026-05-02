# ApiCoreService

## Email verification delivery

By default the service works in development mode: if `SMTP_HOST` is empty, verification codes are written to logs and, when `EXPOSE_DEV_EMAIL_CODE=true`, returned in API responses.

To send real emails, configure SMTP in the root `.env` and rebuild/recreate `api_core_service`.

```env
EXPOSE_DEV_EMAIL_CODE=false
EMAIL_FROM=no-reply@example.com
EMAIL_FROM_NAME=Parser Monitor
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=no-reply@example.com
SMTP_PASSWORD=your-smtp-password-or-app-password
SMTP_USE_SSL=false
SMTP_STARTTLS=true
SMTP_TIMEOUT_SECONDS=10
```

For providers that use implicit SSL, usually set:

```env
SMTP_PORT=465
SMTP_USE_SSL=true
SMTP_STARTTLS=false
```

After changing SMTP variables:

```bash
docker compose up -d --build --force-recreate api_core_service
```

The same email sender is used by login email verification and notification email channel verification.
