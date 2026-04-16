# VPS PostgreSQL configuration notes
# Server: Ubuntu, aarch64, dev2null.de (mail.dev2null.de)
# PostgreSQL version: 17 (system install, not Docker)
#
# pg_hba.conf location: /etc/postgresql/17/main/pg_hba.conf
# postgresql.conf location: /etc/postgresql/17/main/postgresql.conf
#
# Key postgresql.conf settings:
#   listen_addresses = '*'
#   port = 5432
#   max_connections = 100
#   shared_buffers = 128MB
#
# Users and databases (taris-related):
#   User: taris   DB: taris      (CRM/EspoCRM backend)
#   User: taris   DB: taris_vps  (Docker instance — Supertariss bot)
#
# pgvector: INSTALLED (v0.8.0) — enable per-database with:
#   sudo -u postgres psql -d taris_vps -c "CREATE EXTENSION IF NOT EXISTS vector;"
#
# SSH tunnel from SintAItion → VPS:
#   taris-pg-tunnel.service binds SintAItion local 15432 → VPS 5432
#   CRM_PG_DSN=postgresql://taris:PASSWORD@127.0.0.1:15432/taris
#
# Initial setup on new VPS:
#   sudo apt install postgresql postgresql-contrib
#   sudo apt install postgresql-17-pgvector   # or build from source
#   sudo -u postgres psql -c "CREATE USER taris WITH PASSWORD 'PASSWORD';"
#   sudo -u postgres psql -c "CREATE DATABASE taris OWNER taris;"
#   sudo -u postgres psql -c "CREATE DATABASE taris_vps OWNER taris;"
#   sudo -u postgres psql -d taris_vps -c "CREATE EXTENSION IF NOT EXISTS vector;"
#   sudo -u postgres psql -d taris -c "CREATE EXTENSION IF NOT EXISTS vector;"
#   # Update pg_hba.conf to allow Docker bridge networks (see pg_hba.conf in this dir)
