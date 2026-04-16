# VPS PostgreSQL configuration notes
# Server: Ubuntu 24.04 LTS (mail.dev2null.de)
# PostgreSQL version: installed from Ubuntu packages
#
# Key postgresql.conf settings:
#   listen_addresses = '*'
#   port = 5432
#   max_connections = 100
#   shared_buffers = 128MB
#
# pg_hba.conf — connections allowed:
#   local all all peer
#   host  all all 127.0.0.1/32 md5
#   host  all all ::1/128 md5
#
# Users and databases (taris-related):
#   User: taris_user  DB: taris_db  (local 5432 — SintAItion CRM via SSH tunnel)
#   User: taris       DB: taris      (local 5432 — CRM/EspoCRM backend)
#
# SSH tunnel from SintAItion → VPS:
#   SintAItion taris-pg-tunnel.service binds local 15432 → VPS 5432
#   CRM_PG_DSN=postgresql://taris:PASSWORD@127.0.0.1:15432/taris
#
# Initial setup:
#   sudo apt install postgresql postgresql-contrib pgvector
#   sudo -u postgres psql -c "CREATE USER taris_user WITH PASSWORD 'PASSWORD';"
#   sudo -u postgres psql -c "CREATE DATABASE taris_db OWNER taris_user;"
#   sudo -u postgres psql taris_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
