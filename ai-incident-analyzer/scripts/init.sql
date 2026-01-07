-- init postgres schema

CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    alert_name VARCHAR(255),
    category VARCHAR(50),
    severity VARCHAR(20),
    affected_services TEXT[],
    root_causes JSONB,
    steps JSONB,
    summary TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_incidents_ts ON incidents(timestamp DESC);
CREATE INDEX idx_incidents_category ON incidents(category);
CREATE INDEX idx_incidents_severity ON incidents(severity);

-- grant perms
GRANT ALL ON ALL TABLES IN SCHEMA public TO incident_user;
