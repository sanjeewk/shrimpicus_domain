# Shrimpicus Production Deployment Plan

## Overview

This plan outlines how to deploy shrimpicus to production hosting for 10-20 friends with all core features preserved: Discord bot, Flask web interface, multi-user social features, habit tracking, and Ollama AI chat.

## Architecture Changes Summary

### Current (Local Development)
```
┌─────────────────────────────────────────┐
│  Local Machine                          │
│  ├─ Discord Bot (async process)         │
│  ├─ Flask Web App (dev server :5005)    │
│  ├─ SQLite Database (./data/)           │
│  ├─ Ollama (local :11434)               │
│  └─ APScheduler (reminder polling)      │
└─────────────────────────────────────────┘
```

### Production (Hosted)
```
┌──────────────────────────────────────────────────────────────┐
│  VPS / Cloud VM (e.g., DigitalOcean, Linode, Hetzner)       │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Docker Container 1: Discord Bot + Scheduler        │    │
│  │  (shrimpicus bot process)                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Docker Container 2: Web App                        │    │
│  │  Gunicorn + Flask (:8000)                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Nginx Reverse Proxy (:80, :443)                    │    │
│  │  SSL termination, static file serving               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  PostgreSQL Database                                │    │
│  │  (replaces SQLite for multi-user reliability)       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Ollama Server (:11434)                             │    │
│  │  GPU-accelerated or CPU-based inference             │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Shared Volume: /data (database, uploads, logs)             │
└──────────────────────────────────────────────────────────────┘
```

## Required Changes

### 1. Database Migration: SQLite → PostgreSQL

**Why:** SQLite has `check_same_thread=False` which works locally but causes concurrency issues under load. PostgreSQL provides proper ACID guarantees for multiple concurrent users.

**Files to modify:**
- `shrimpicus/db.py` - Add PostgreSQL adapter using `psycopg2`
- `shrimpicus/config.py` - Add `DATABASE_URL` environment variable
- `shrimpicus/web/app.py` - Update connection logic

**Implementation:**
```python
# New database connection logic (pseudo-code)
if DATABASE_URL.startswith('postgresql://'):
    # Use psycopg2
    conn = psycopg2.connect(DATABASE_URL)
else:
    # Fall back to SQLite for local dev
    conn = sqlite3.connect(db_path)
```

### 2. Production Web Server

**Current:** Flask development server (`app.run()`)  
**Production:** Gunicorn WSGI server behind Nginx

**New files to create:**
- `gunicorn.conf.py` - Gunicorn configuration
- `nginx.conf` - Nginx reverse proxy configuration
- `Dockerfile.web` - Web app container

### 3. Process Isolation

**Current:** Single `main.py` runs everything together  
**Production:** Separate processes for bot and web app

**Reason:** Discord bot and web app have different scaling needs. Bot needs 1 instance (stateful), web can scale horizontally.

**New entrypoints:**
- `shrimpicus-bot` - Runs only the Discord bot + scheduler
- `shrimpicus-web` - Already exists, runs only Flask

### 4. Remove Local-Only Features

**Obsidian Integration:** Remove or make fully optional (requires local filesystem access)  
**Notion Integration:** Keep but make optional (API-based, works remotely)  
**Voice Transcription:** Keep but warn about CPU usage

### 5. Configuration Management

**Current:** `.env` file with relative paths  
**Production:** Environment variables via Docker Compose or cloud secrets manager

**New `.env.production` template:**
```bash
# Discord
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_COMMAND_PREFIX=!
ASSISTANT_CHANNELS=general

# Database
DATABASE_URL=postgresql://user:password@postgres:5432/shrimpicus

# Ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M

# Web Server
WEB_HOST=0.0.0.0
WEB_PORT=8000
SECRET_KEY=generate_long_random_string_here

# Security
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true

# Optional integrations
NOTION_TOKEN=
NOTION_DATABASE_ID=
WHISPER_ENABLED=false
```

### 6. Docker Containerization

**New files:**
- `Dockerfile` - Bot container
- `Dockerfile.web` - Web app container
- `docker-compose.yml` - Orchestrates all services
- `.dockerignore` - Exclude unnecessary files

## Hosting Platform Recommendations

### Option 1: DigitalOcean Droplet (Recommended for your needs)

**Specs:** 4 vCPU, 8GB RAM, 160GB SSD ($48/month)  
**Why:** Ollama needs significant RAM (6-8GB for 7B model). Good balance of cost and performance.

**Pros:**
- Full control, can run Ollama with good performance
- Easy setup with Docker
- Predictable pricing
- Good documentation

**Cons:**
- Manual server management required
- Need to handle security updates
- Single point of failure (add backups)

**Setup Steps:**
1. Create Ubuntu 22.04 droplet
2. Install Docker & Docker Compose
3. Clone repo, add `.env.production`
4. Run `docker-compose up -d`
5. Configure domain DNS
6. Set up Let's Encrypt SSL via Certbot

### Option 2: Hetzner Cloud (Lower cost alternative)

**Specs:** CPX31 (4 vCPU, 8GB RAM, 160GB disk - €13.45/month, ~$15/month)  
**Why:** Similar specs to DigitalOcean but 70% cheaper. Europe-based.

**Pros:**
- Significantly cheaper
- Excellent performance for price
- Docker-ready Ubuntu images

**Cons:**
- Servers in Europe (higher latency if you're in US/Asia)
- Less popular than DigitalOcean (but still reliable)

### Option 3: AWS Lightsail

**Specs:** 2 vCPU, 8GB RAM ($40/month)  
**Why:** Good middle ground, managed AWS with simple pricing.

**Pros:**
- AWS reliability
- Simple pricing
- Managed database option available

**Cons:**
- Slightly more expensive
- 2 vCPU might be marginal for Ollama
- AWS complexity if you need to scale

### Option 4: Railway.app (Hybrid approach)

**Cost:** ~$30-50/month estimated  
**Why:** Modern PaaS, easy deployment from Git.

**Architecture:**
- Web app: Railway ($5-10/month)
- Discord bot: Railway ($5-10/month)
- PostgreSQL: Railway managed DB ($10/month)
- Ollama: Separate VPS required (Railway doesn't support GPU, high RAM expensive)

**Pros:**
- Dead simple deployment (connect GitHub, auto-deploy)
- Built-in PostgreSQL
- No server management
- Automatic HTTPS

**Cons:**
- Ollama still needs a separate VPS
- More expensive for the specs
- Less control

### Option 5: Render.com (Alternative PaaS)

**Cost:** Similar to Railway ($30-40/month)  
**Why:** Vercel-like experience for full-stack apps.

**Pros:**
- Free PostgreSQL (with limits)
- Easy Discord bot hosting
- Auto-deploys from Git
- Free SSL

**Cons:**
- Ollama needs separate hosting
- Free PostgreSQL limited to 90 days, then $7/month

### ⚠️ Why NOT Vercel/Netlify

Vercel and Netlify are **static/serverless platforms** designed for:
- Static sites
- Serverless functions (short-lived, <10s execution)
- Edge compute

**Why shrimpicus doesn't fit:**
1. **Long-running processes:** Discord bot runs 24/7 listening to events
2. **Stateful scheduler:** APScheduler maintains in-memory state
3. **WebSocket connections:** Discord.py uses persistent WebSocket connection
4. **Ollama:** Requires persistent server with 6-8GB RAM
5. **Database writes:** High-frequency reminder polling and habit tracking

Vercel could theoretically host:
- Static web UI (frontend only)
- API routes as serverless functions

But you'd still need:
- Separate VPS for Discord bot
- Separate VPS for Ollama
- Managed database (PlanetScale, Supabase)
- This defeats the purpose and is more expensive.

## Recommended Hosting Solution

**For 10-20 friends with full features:**

### Primary Recommendation: Hetzner Cloud VPS + Docker

**Server:** Hetzner CPX31 (4 vCPU, 8GB RAM) - €13.45/month  
**Domain:** Namecheap/Cloudflare (~$12/year)  
**Backups:** Hetzner automated backups (+20% = €2.69/month)  
**Total:** ~$18/month

**What you get:**
- ✅ All features working (Discord bot, web app, Ollama, habits, social)
- ✅ PostgreSQL database
- ✅ SSL certificates (free via Let's Encrypt)
- ✅ Docker orchestration
- ✅ Room to grow to 50+ users
- ✅ Full control

### Deployment Steps

1. **Provision Server**
   ```bash
   # Create Hetzner cloud server via web UI
   # Choose: Ubuntu 22.04, CPX31, enable backups
   ```

2. **Initial Server Setup**
   ```bash
   ssh root@your_server_ip
   
   # Update system
   apt update && apt upgrade -y
   
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   
   # Install Docker Compose
   apt install docker-compose-plugin -y
   
   # Create app user
   adduser --disabled-password shrimpicus
   usermod -aG docker shrimpicus
   ```

3. **Clone Repository**
   ```bash
   su - shrimpicus
   git clone https://github.com/yourusername/shrimpicus.git
   cd shrimpicus
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env.production
   nano .env.production
   # Fill in Discord bot token, secrets, etc.
   ```

5. **Start Services**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

6. **Configure Domain & SSL**
   ```bash
   # Point domain A record to server IP
   # Install Certbot
   sudo apt install certbot python3-certbot-nginx -y
   sudo certbot --nginx -d yourdomain.com
   ```

7. **Set Up Monitoring**
   ```bash
   # Install monitoring (optional but recommended)
   docker-compose logs -f  # View logs
   ```

## Implementation Checklist

### Phase 1: Code Changes (Local Development)
- [ ] Add PostgreSQL adapter to `db.py`
- [ ] Create database migration script (SQLite → PostgreSQL)
- [ ] Update `config.py` for `DATABASE_URL` support
- [ ] Create `shrimpicus-bot` entrypoint
- [ ] Update `web/app.py` for production configuration
- [ ] Remove Obsidian integration or make fully optional
- [ ] Create `requirements.txt` for production dependencies
- [ ] Add `gunicorn.conf.py`

### Phase 2: Dockerization
- [ ] Create `Dockerfile` for bot
- [ ] Create `Dockerfile.web` for web app
- [ ] Create `docker-compose.yml` for local testing
- [ ] Create `docker-compose.prod.yml` for production
- [ ] Create `nginx.conf` for reverse proxy
- [ ] Create `.dockerignore`
- [ ] Test locally with Docker Compose

### Phase 3: Infrastructure Setup
- [ ] Create Hetzner account
- [ ] Provision CPX31 server
- [ ] Configure firewall (ports 22, 80, 443)
- [ ] Set up SSH keys
- [ ] Install Docker & Docker Compose
- [ ] Set up domain DNS

### Phase 4: Deployment
- [ ] Clone repository to server
- [ ] Configure `.env.production`
- [ ] Run database migrations
- [ ] Start services with Docker Compose
- [ ] Configure Nginx reverse proxy
- [ ] Set up SSL with Let's Encrypt
- [ ] Test all features (Discord bot, web app, Ollama)

### Phase 5: Operations
- [ ] Set up automated backups
- [ ] Configure log rotation
- [ ] Set up monitoring (Uptime Robot, Grafana)
- [ ] Document deployment process
- [ ] Create runbook for common issues
- [ ] Set up alerts for downtime

## Security Considerations

1. **Secrets Management**
   - Use strong random secret key for Flask sessions
   - Store Discord bot token securely (environment variable, not in code)
   - Enable PostgreSQL password authentication

2. **Network Security**
   - Configure UFW firewall: allow only 22, 80, 443
   - Use SSH keys, disable password authentication
   - Keep PostgreSQL unexposed (Docker internal network only)

3. **Application Security**
   - Enable session cookie security flags (httponly, secure)
   - Use Argon2 password hashing (already implemented)
   - Rate limit login attempts (add Flask-Limiter)
   - Validate all user inputs (check existing validation)

4. **Updates**
   - Set up unattended-upgrades for security patches
   - Pin Docker image versions, update intentionally
   - Subscribe to Discord.py security advisories

## Cost Breakdown (Monthly)

**Hetzner Solution:**
| Item | Cost |
|------|------|
| Hetzner CPX31 | €13.45 (~$15) |
| Automated backups | €2.69 (~$3) |
| Domain (amortized) | $1 |
| **Total** | **~$18-19/month** |

**Alternative Solutions for Comparison:**

| Platform | Monthly Cost | Notes |
|----------|--------------|-------|
| DigitalOcean Droplet | $48 | Same specs, US-based |
| AWS Lightsail | $40 | 2 vCPU only |
| Railway + VPS | $40-60 | Split hosting |
| Dedicated server | $50-100 | Overkill for 20 users |

## Performance Expectations

**With Hetzner CPX31 (4 vCPU, 8GB RAM):**

- **Ollama inference:** 2-5 seconds per query (7B model, CPU)
- **Web response time:** <200ms for most requests
- **Discord bot latency:** <500ms for commands
- **Concurrent users:** 20-30 comfortably, up to 50 peak
- **Database:** Thousands of todos/habits/reminders no problem

**Bottlenecks to watch:**
1. Ollama CPU usage (largest resource consumer)
2. PostgreSQL connections (tune `max_connections` if needed)
3. Disk I/O (160GB SSD should be fine)

## Monitoring & Maintenance

**Essential monitoring:**
- Uptime Robot (free tier) - ping web app every 5 minutes
- Docker logs - `docker-compose logs -f`
- Disk usage - `df -h` (alert if >80%)
- PostgreSQL backup verification

**Maintenance schedule:**
- Daily: Check logs for errors
- Weekly: Review disk usage, backup status
- Monthly: Security updates (`apt upgrade`)
- Quarterly: Review costs, optimize if needed

## Migration Path (SQLite → PostgreSQL)

**Script to migrate existing data:**

```bash
#!/bin/bash
# migration.sh

# 1. Export SQLite to SQL dump
sqlite3 data/shrimpicus.db .dump > backup.sql

# 2. Clean up SQLite-specific syntax
sed -i 's/AUTOINCREMENT/SERIAL/g' backup.sql
sed -i 's/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/g' backup.sql

# 3. Import to PostgreSQL
psql $DATABASE_URL < backup.sql

# 4. Verify row counts match
echo "Verify migration:"
sqlite3 data/shrimpicus.db "SELECT COUNT(*) FROM todos;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM todos;"
```

## Rollback Plan

If production deployment fails:

1. **Keep local instance running** - Don't shut down local bot until production is verified
2. **Database backup** - Always export SQLite before migration
3. **Docker volumes** - Production data persists in volumes, can be exported
4. **Quick rollback**: Delete server, restore local instance (5 minutes)

## Future Scaling Options

**When you outgrow single VPS:**

1. **Horizontal scaling (50+ users):**
   - Keep bot on single server (stateful)
   - Scale web app horizontally (multiple containers + load balancer)
   - Managed PostgreSQL (DigitalOcean/AWS RDS)

2. **Add GPU for Ollama:**
   - Hetzner doesn't offer GPU instances
   - Move Ollama to separate GPU-enabled VPS (Vast.ai, Paperspace)
   - Or switch to API-based LLM (OpenAI, Anthropic) - easier but recurring cost

3. **CDN for static assets:**
   - Add Cloudflare in front of Nginx (free tier)
   - Cache static CSS/JS/images
   - DDoS protection

## Conclusion

**Recommended approach:**
1. Use **Hetzner CPX31** for hosting ($15-18/month)
2. Implement **Docker Compose** orchestration
3. Migrate to **PostgreSQL** for reliability
4. Deploy all services on single VPS (bot, web, db, Ollama)
5. Use **Nginx + Let's Encrypt** for HTTPS

**Timeline estimate:**
- Code changes: 1-2 days
- Docker setup: 1 day
- Deployment & testing: 1 day
- Total: 3-4 days of focused work

**Next steps:**
1. Create Hetzner account
2. Implement Phase 1 (code changes)
3. Test locally with Docker
4. Deploy to production server
5. Invite friends!

---

**Questions or need help with specific steps?** Let me know which phase to start with.
