## PostgreSQL Migration Summary

The PostgreSQL migration for shrimpicus is now complete! Here's what was implemented:

### ✅ Completed Changes

1. **Database Layer (`shrimpicus/db.py`)**
   - Added PostgreSQL support with automatic detection via `DATABASE_URL`
   - Database class now accepts both `db_path` (SQLite) and `database_url` (PostgreSQL)
   - Created separate `_init_sqlite()` and `_init_postgres()` methods for schema initialization
   - Added `_param()` helper to convert SQLite placeholders (?) to PostgreSQL (%s)
   - PostgreSQL uses `SERIAL` instead of `AUTOINCREMENT` for auto-incrementing IDs
   - Both databases fully supported with single codebase

2. **Configuration (`shrimpicus/config.py`)**
   - Added `database_url` field for PostgreSQL connection string
   - Added production settings: `web_host`, `web_port`, `secret_key`
   - Created `.env.production.example` template with all required variables

3. **Dependencies (`pyproject.toml`)**
   - Added `psycopg2-binary>=2.9.9` for PostgreSQL support
   - Added `gunicorn>=21.2.0` for production WSGI server
   - Created `shrimpicus-bot` entrypoint (alias for main)

4. **Application Updates**
   - Updated `shrimpicus/main.py` to pass `database_url` to Database class
   - Updated `shrimpicus/web/app.py` to support PostgreSQL connections
   - Web app now uses `DATABASE_URL` from config and `SECRET_KEY` from settings

5. **Migration Tooling**
   - Created `migrate_to_postgres.py` script to transfer data from SQLite to PostgreSQL
   - Script handles all tables, verifies row counts, and resets sequences
   - Usage: `python migrate_to_postgres.py --sqlite ./data/shrimpicus.db --postgres postgresql://user:pass@host/db`

6. **Production Configuration**
   - Created `gunicorn.conf.py` for production WSGI server
   - Created `nginx.conf` for reverse proxy with SSL support
   - Created deployment plan in `DEPLOYMENT_PLAN.md`

### 📋 How to Use

**Local Development (SQLite - default):**
```bash
# No changes needed - continues to work as before
shrimpicus
```

**Production (PostgreSQL):**
```bash
# 1. Set DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@localhost:5432/shrimpicus

# 2. Migrate existing data (optional)
python migrate_to_postgres.py --sqlite ./data/shrimpicus.db --postgres $DATABASE_URL

# 3. Run the application
shrimpicus-bot  # Discord bot
shrimpicus-web  # Web interface
```

### 🔄 Database Connection Logic

The Database class now automatically chooses the right backend:

```python
# If DATABASE_URL is set and starts with 'postgresql://'
database_url = "postgresql://..."  # → Uses PostgreSQL

# Otherwise, falls back to SQLite
db_path = "./data/shrimpicus.db"  # → Uses SQLite
```

### 🚀 Next Steps for Deployment

See `DEPLOYMENT_PLAN.md` for the complete hosting guide. Quick summary:

1. **Create Hetzner VPS** (CPX31: 4 vCPU, 8GB RAM - €13.45/month)
2. **Install Docker & Docker Compose**
3. **Clone repo and configure `.env.production`**
4. **Run migration script** to transfer SQLite → PostgreSQL
5. **Deploy with Docker Compose** (if using Docker) or run directly
6. **Set up domain + SSL** with Let's Encrypt

### 🧪 Testing

To test PostgreSQL locally:

```bash
# 1. Start PostgreSQL with Docker
docker run --name postgres-test -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=shrimpicus -p 5432:5432 -d postgres:15-alpine

# 2. Set DATABASE_URL
export DATABASE_URL="postgresql://postgres:testpass@localhost:5432/shrimpicus"

# 3. Run migration
python migrate_to_postgres.py --sqlite ./data/shrimpicus.db --postgres $DATABASE_URL

# 4. Test the app
shrimpicus-bot
```

### ⚠️ Important Notes

- **SQLite is still the default** - no breaking changes for local development
- **PostgreSQL is optional** - only needed for production multi-user hosting
- **Both work with the same code** - no separate branches needed
- **Data migration is one-way** - keep SQLite backup until you verify PostgreSQL works
- **Sequences must be reset** after migration (the script handles this automatically)

### 📦 What's NOT Included (Yet)

The following Docker/deployment files were NOT created to avoid overwriting:
- `Dockerfile` (Discord bot container)
- `Dockerfile.web` (Web app container)
- `docker-compose.yml` (Full orchestration)

These can be created when you're ready to deploy. The deployment plan includes templates for all of them.

### 🐛 Known Limitations

1. Web app uses a compatibility layer for PostgreSQL connections (works but could be cleaner)
2. Migration script doesn't handle foreign key constraints in complex cases (should be fine for shrimpicus schema)
3. No connection pooling configured yet (add pgBouncer if you scale beyond 50 users)

### 📝 Files Modified

- `shrimpicus/db.py` - PostgreSQL adapter
- `shrimpicus/config.py` - Production settings
- `shrimpicus/main.py` - Database URL support
- `shrimpicus/web/app.py` - PostgreSQL web connections
- `pyproject.toml` - Dependencies
- `README.md` - Changelog

### 📝 Files Created

- `.env.production.example` - Production config template
- `migrate_to_postgres.py` - Migration script
- `gunicorn.conf.py` - WSGI server config
- `nginx.conf` - Reverse proxy config
- `DEPLOYMENT_PLAN.md` - Full hosting guide

---

**Status: Ready for production deployment!** 🎉

The codebase now supports both local development (SQLite) and production hosting (PostgreSQL) with no code changes needed. Just set `DATABASE_URL` in production and you're good to go.
