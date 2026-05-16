-- Create a separate database and user for Airflow metadata.
-- This script runs as POSTGRES_USER (wine_user) on first container start.

CREATE USER airflow WITH PASSWORD 'airflow';
CREATE DATABASE airflow OWNER airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;
