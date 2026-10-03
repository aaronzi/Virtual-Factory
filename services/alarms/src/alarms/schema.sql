-- Alarms & events database (TimescaleDB, ADR-0026). Created idempotently by the alarms service at start.
-- Hypertables: alarm_journal, event_journal (append-only, time-partitioned, retention policies).
-- Plain tables: alarm_definition (master alarm database), alarm_state (current state per alarm, updated in
-- place), alarm_occurrence (one row per activation, updated on acknowledge / return to normal).
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS alarm_definition (
    code               integer PRIMARY KEY,
    source             text NOT NULL,
    text_en            text NOT NULL,
    text_de            text NOT NULL,
    priority           text NOT NULL,
    priority_rank      smallint NOT NULL,
    alarm_class        text,
    reaction           text,
    response_s         integer,
    remedy_en          text,
    remedy_de          text,
    suppressed_by      integer[] NOT NULL DEFAULT '{}',
    suppress_in_states integer[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS alarm_occurrence (
    id            bigserial PRIMARY KEY,
    code          integer NOT NULL REFERENCES alarm_definition (code),
    session       text,
    priority      text NOT NULL,
    activated_at  timestamptz NOT NULL,
    annunciated   boolean NOT NULL,
    acked_at      timestamptz,
    acked_by      text,
    cleared_at    timestamptz
);
CREATE INDEX IF NOT EXISTS alarm_occurrence_activated ON alarm_occurrence (activated_at DESC);
CREATE INDEX IF NOT EXISTS alarm_occurrence_code ON alarm_occurrence (code, activated_at DESC);

CREATE TABLE IF NOT EXISTS alarm_state (
    code           integer PRIMARY KEY REFERENCES alarm_definition (code),
    state          text NOT NULL,
    active         boolean NOT NULL,
    acked          boolean NOT NULL,
    suppressed     boolean NOT NULL,
    shelved_until  timestamptz,
    shelved_by     text,
    activated_at   timestamptz,
    acked_at       timestamptz,
    acked_by       text,
    cleared_at     timestamptz,
    occurrence_id  bigint,
    session        text,
    comment        text,
    updated_at     timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS alarm_journal (
    time           timestamptz NOT NULL,
    code           integer NOT NULL,
    event          text NOT NULL,
    state          text NOT NULL,
    priority       text NOT NULL,
    annunciated    boolean NOT NULL,
    operator       text,
    comment        text,
    session        text,
    occurrence_id  bigint
);
SELECT create_hypertable('alarm_journal', by_range('time', INTERVAL '1 day'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS alarm_journal_code ON alarm_journal (code, time DESC);

CREATE TABLE IF NOT EXISTS event_journal (
    time         timestamptz NOT NULL,
    kind         text NOT NULL,          -- event | command | ack | state | session | status
    device       text,
    name         text,
    topic        text NOT NULL,
    session      text,
    seq          integer,
    source_time  timestamptz,
    payload      jsonb
);
SELECT create_hypertable('event_journal', by_range('time', INTERVAL '1 day'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS event_journal_name ON event_journal (name, time DESC);

SELECT add_retention_policy('alarm_journal', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('event_journal', INTERVAL '30 days', if_not_exists => TRUE);

-- read-only login for Grafana (data source "Alarms & events (TimescaleDB)")
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana') THEN
        CREATE ROLE grafana LOGIN PASSWORD 'grafana-local-only';
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO grafana;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana;
