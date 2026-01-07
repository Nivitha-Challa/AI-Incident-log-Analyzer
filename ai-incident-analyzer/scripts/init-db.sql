-- Database initialization script for Incident Analyzer

-- Create incidents table
CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    alert_name VARCHAR(255) NOT NULL,
    classification VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    affected_services TEXT[],
    root_causes JSONB,
    remediation_steps JSONB,
    summary TEXT,
    confidence_score DECIMAL(3, 2),
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create index on timestamp for faster queries
CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON incidents(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_classification ON incidents(classification);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_resolved ON incidents(resolved);

-- Create table for storing metrics snapshots
CREATE TABLE IF NOT EXISTS incident_metrics (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) REFERENCES incidents(incident_id),
    metric_name VARCHAR(255) NOT NULL,
    metric_values JSONB,
    labels JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_metrics_incident_id ON incident_metrics(incident_id);

-- Create table for storing log snapshots
CREATE TABLE IF NOT EXISTS incident_logs (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) REFERENCES incidents(incident_id),
    log_level VARCHAR(20),
    log_message TEXT,
    log_timestamp TIMESTAMP,
    service VARCHAR(100),
    labels JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_logs_incident_id ON incident_logs(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_logs_timestamp ON incident_logs(log_timestamp DESC);

-- Create table for incident relationships (similar incidents)
CREATE TABLE IF NOT EXISTS incident_relationships (
    id SERIAL PRIMARY KEY,
    incident_id_1 VARCHAR(50) REFERENCES incidents(incident_id),
    incident_id_2 VARCHAR(50) REFERENCES incidents(incident_id),
    similarity_score DECIMAL(3, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(incident_id_1, incident_id_2)
);

CREATE INDEX IF NOT EXISTS idx_relationships_incident_1 ON incident_relationships(incident_id_1);

-- Create table for tracking remediation actions
CREATE TABLE IF NOT EXISTS remediation_actions (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) REFERENCES incidents(incident_id),
    step_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,
    executed_by VARCHAR(100),
    result TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_remediation_incident_id ON remediation_actions(incident_id);

-- Create table for AI analysis metrics
CREATE TABLE IF NOT EXISTS ai_analysis_metrics (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) REFERENCES incidents(incident_id),
    analysis_duration_seconds DECIMAL(10, 2),
    model_used VARCHAR(100),
    tokens_used INTEGER,
    api_cost DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_metrics_incident_id ON ai_analysis_metrics(incident_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for auto-updating updated_at
CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create view for incident statistics
CREATE OR REPLACE VIEW incident_statistics AS
SELECT 
    DATE_TRUNC('day', timestamp) as date,
    classification,
    severity,
    COUNT(*) as count,
    AVG(confidence_score) as avg_confidence,
    COUNT(CASE WHEN resolved THEN 1 END) as resolved_count,
    AVG(EXTRACT(EPOCH FROM (resolved_at - timestamp))) as avg_resolution_time_seconds
FROM incidents
GROUP BY DATE_TRUNC('day', timestamp), classification, severity;

-- Insert sample data for testing (optional)
-- INSERT INTO incidents (incident_id, alert_name, classification, severity, summary, confidence_score)
-- VALUES 
--     ('test001', 'HighCPUUsage', 'infrastructure', 'warning', 'Test incident for development', 0.85),
--     ('test002', 'ServiceDown', 'application', 'critical', 'Test critical incident', 0.92);

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO incident_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO incident_user;
