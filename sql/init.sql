-- Create tables for Policy Discovery System

CREATE DATABASE n8n;

CREATE TABLE IF NOT EXISTS companies (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL UNIQUE,
    generic_email VARCHAR(255),
    contact_email VARCHAR(255),
    privacy_email VARCHAR(255),
    delete_link TEXT,
    country VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    processed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS policy_pages (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) REFERENCES companies(id),
    url TEXT NOT NULL,
    page_type VARCHAR(50), -- 'privacy', 'terms', 'other'
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, page_type)
);

CREATE TABLE IF NOT EXISTS policy_scopes (
    company_id VARCHAR(255) REFERENCES companies(id) PRIMARY KEY,
    scope_registration BOOLEAN DEFAULT FALSE,
    scope_legal BOOLEAN DEFAULT FALSE,
    scope_customization BOOLEAN DEFAULT FALSE,
    scope_marketing BOOLEAN DEFAULT FALSE,
    scope_security BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processing_log (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) REFERENCES companies(id),
    step VARCHAR(50),
    status VARCHAR(50),
    message TEXT,
    duration_seconds FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
