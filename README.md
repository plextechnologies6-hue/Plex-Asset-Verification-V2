# Plex Technologies – Asset Verification Platform V2

Version 2 introduces:
- Plex Technologies branding/logo
- PostgreSQL-ready database architecture
- Client management
- Multiple verification sessions per client
- Session-isolated FAR and field asset records
- FAR import into a selected session
- Field asset capture linked to a session
- FAR reconciliation per session
- Field-register CSV export
- Responsive dashboard

## Local setup
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app falls back to SQLite locally if DATABASE_URL is not set.

## Render + PostgreSQL
1. Deploy this repository as a Render Web Service.
2. Create a Render Postgres database in the same region.
3. Copy the database's internal connection URL.
4. Add a Render environment variable:
   DATABASE_URL=<internal postgres URL>
5. Add:
   SECRET_KEY=<long random secret>
6. Deploy.

## Important
This is a V2 foundation, not a final production system. Before live client use, add authentication/roles, audit logs, object storage for photos, offline/PWA synchronization, native XLSX import/export, backups, and stronger validation.
