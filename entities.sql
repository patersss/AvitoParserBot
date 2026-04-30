CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- API service
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    username            VARCHAR(150),
    avatar_url          TEXT,

    login_email         VARCHAR(255) UNIQUE,
    password_hash       TEXT,
    is_email_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    user_role           varchar(30) DEFAULT 'user',

    status              VARCHAR(30) NOT NULL DEFAULT 'active',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,

    CHECK (status IN ('active', 'banned', 'deleted')),

    CHECK (user_role IN ('user', 'admin', 'superadmin')),

    CHECK (
        login_email IS NULL
        OR password_hash IS NOT NULL
    )
);

CREATE INDEX idx_users_login_email
ON users(login_email);

CREATE INDEX idx_users_status
ON users(status);

CREATE INDEX idx_users_deleted_at
ON users(deleted_at);

CREATE TABLE telegram_accounts (
    user_id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,

    telegram_user_id    BIGINT NOT NULL UNIQUE,
    chat_id             BIGINT NOT NULL UNIQUE,

    username            VARCHAR(100)

);

CREATE INDEX idx_telegram_accounts_telegram_user_id
ON telegram_accounts(telegram_user_id);

CREATE TABLE login_tokens (
    token_hash         TEXT PRIMARY KEY,

    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    purpose            VARCHAR(50) NOT NULL,

    expires_at         TIMESTAMPTZ NOT NULL,
    used_at            TIMESTAMPTZ,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX idx_login_tokens_user_id
ON login_tokens(user_id);


CREATE TABLE email_verifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,

    email           VARCHAR(255) NOT NULL,
    code_hash       TEXT NOT NULL,

    purpose         VARCHAR(50) NOT NULL,

    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,

    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (purpose IN (
        'set_login_email',
        'set_notification_email',
        'reset_password',
        'change_login_email'
    )),

    CHECK (attempts >= 0),
    CHECK (max_attempts > 0)
);

CREATE INDEX idx_email_verifications_user_id
ON email_verifications(user_id);

CREATE INDEX idx_email_verifications_email
ON email_verifications(email);


CREATE TABLE notification_channels (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    type           VARCHAR(30) NOT NULL,
    config         JSONB NOT NULL,

    is_active      BOOLEAN NOT NULL DEFAULT TRUE,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at     TIMESTAMPTZ,

    UNIQUE(user_id, type),

    CHECK (type IN ('telegram', 'email', 'vk'))
);

CREATE INDEX idx_notification_channels_user_id
ON notification_channels(user_id);


CREATE TABLE tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name              VARCHAR(150),

    platform          VARCHAR(30) NOT NULL,
    url               TEXT NOT NULL,

    interval_minutes  INTEGER NOT NULL DEFAULT 30,

    end_date          TIMESTAMPTZ,

    is_active         BOOLEAN NOT NULL DEFAULT TRUE,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ,

    CHECK (platform IN ('avito', 'cian', 'youla')),
    CHECK (interval_minutes > 0)
);

CREATE INDEX idx_tasks_user_id
ON tasks(user_id);


CREATE TABLE listings_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,

    platform        VARCHAR(30) NOT NULL,
    external_id     VARCHAR(150) NOT NULL,

    title           TEXT NOT NULL,
    price           BIGINT,

    url             TEXT NOT NULL,
    image_url       TEXT,

    published_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(task_id, platform, external_id),

    CHECK (platform IN ('avito', 'cian', 'youla'))
);

CREATE TABLE outbox_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    event_type      VARCHAR(100) NOT NULL,
    aggregate_type  VARCHAR(100) NOT NULL,
    aggregate_id    UUID NOT NULL,

    routing_key     VARCHAR(150) NOT NULL,

    payload         JSONB NOT NULL,

    status          VARCHAR(30) NOT NULL DEFAULT 'pending',

    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 10,

    next_retry_at   TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,

    error           TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN ('pending', 'published', 'failed')),
    CHECK (attempts >= 0),
    CHECK (max_attempts > 0)
);


CREATE TABLE inbox_events (
    event_id        UUID PRIMARY KEY,

    event_type      VARCHAR(100) NOT NULL,
    source_service  VARCHAR(100) NOT NULL,

    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,

    status          VARCHAR(30) NOT NULL DEFAULT 'received',

    error           TEXT,

    CHECK (status IN ('received', 'processed', 'failed'))
);

-- Parsing service

CREATE TABLE tasks_cache (
    task_id           UUID PRIMARY KEY,

    user_id           UUID NOT NULL,

    platform          VARCHAR(30) NOT NULL,
    url               TEXT NOT NULL,

    name              VARCHAR(150),

    interval_minutes  INTEGER NOT NULL,

    end_date          TIMESTAMPTZ,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,

    next_run_at       TIMESTAMPTZ NOT NULL,

    last_run_at       TIMESTAMPTZ,

    CHECK (platform IN ('avito', 'cian', 'youla')),
    CHECK (interval_minutes > 0)
);

CREATE INDEX idx_tasks_cache_next_run
ON tasks_cache(is_active, next_run_at);

CREATE TABLE found_listings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id         UUID NOT NULL,
    task_id         UUID NOT NULL,

    platform        VARCHAR(30) NOT NULL,
    external_id     VARCHAR(150) NOT NULL,

    title           TEXT,
    price           BIGINT,

    url             TEXT NOT NULL,
    image_url       TEXT,

    published_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(task_id, platform, external_id),

    CHECK (platform IN ('avito', 'cian', 'youla'))
);

CREATE INDEX idx_found_listings_task_id
ON found_listings(task_id);


CREATE TABLE outbox_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    event_type      VARCHAR(100) NOT NULL,
    aggregate_type  VARCHAR(100) NOT NULL,
    aggregate_id    UUID NOT NULL,

    routing_key     VARCHAR(150) NOT NULL,

    payload         JSONB NOT NULL,

    status          VARCHAR(30) NOT NULL DEFAULT 'pending',

    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 10,

    next_retry_at   TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,

    error           TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN ('pending', 'published', 'failed')),
    CHECK (attempts >= 0),
    CHECK (max_attempts > 0)
);

CREATE TABLE inbox_events (
    event_id        UUID PRIMARY KEY,

    event_type      VARCHAR(100) NOT NULL,
    source_service  VARCHAR(100) NOT NULL,

    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,

    status          VARCHAR(30) NOT NULL DEFAULT 'received',

    error           TEXT,

    CHECK (status IN ('received', 'processed', 'failed'))
);

-- Notification service

CREATE TABLE user_channels_cache (
    user_id       UUID NOT NULL,

    type          VARCHAR(30) NOT NULL,

    config        JSONB NOT NULL,

    is_active     BOOLEAN NOT NULL DEFAULT TRUE,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL,

    PRIMARY KEY(user_id, type),

    CHECK (type IN ('telegram', 'email', 'vk'))
);

CREATE INDEX idx_user_channels_cache_user_id
ON user_channels_cache(user_id);

CREATE TABLE inbox_events (
    event_id        UUID PRIMARY KEY,

    event_type      VARCHAR(100) NOT NULL,
    source_service  VARCHAR(100) NOT NULL,

    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,

    status          VARCHAR(30) NOT NULL DEFAULT 'received',

    error           TEXT,

    CHECK (status IN ('received', 'processed', 'failed'))
);