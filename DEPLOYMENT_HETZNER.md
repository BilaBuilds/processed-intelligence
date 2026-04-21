# ProcessEd Tender Engine — Hetzner Production Deployment

**Target Server:** `thinker-AI-prod` (Hetzner Console)  
**OS:** Ubuntu 22.04 LTS  
**Deployment Date:** April 2026  
**Scope:** Production-only execution (no local PC dependency)

---

## 1. DEPLOYMENT STATUS

**✅ Scheduled run stopped.** The "tender-pipeline-daily" Cowork task is disabled. All execution now moves to Hetzner only.

---

## 2. ARCHITECTURE OVERVIEW

The pipeline executes as a **systemd timer** (daily 9am UTC) on the Hetzner server. Each run:
1. Ingests from Contracts Finder + Find a Tender APIs
2. Normalizes, scores, selects, makes decisions, deduplicates
3. Notifies Discord (non-fatal if it fails)
4. Writes manifest + artifacts to persistent storage
5. Cleans up old run files (7-day retention)

**Key properties:**
- Python 3.11+
- No GUI, no desktop dependencies
- All config via environment variables
- Logs to `/var/log/tender-engine/`
- Runs as unprivileged user `tenderer`
- Secrets in `/etc/tender-engine/.env` (600 perms)

---

## 3. SERVER SETUP COMMANDS

### 3.1 System packages

```bash
#!/bin/bash
set -e

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python + build tools
sudo apt-get install -y \
  python3.11 \
  python3.11-venv \
  python3.11-dev \
  build-essential \
  git \
  curl \
  jq \
  systemd-container

# Verify Python
python3.11 --version
```

### 3.2 Create unprivileged user

```bash
sudo useradd -m -s /bin/bash -d /home/tenderer tenderer
sudo mkdir -p /home/tenderer/.ssh
sudo chmod 700 /home/tenderer/.ssh
```

### 3.3 Clone repository

```bash
cd /opt
sudo git clone https://github.com/bilal-li/tender-engine.git tender-engine
sudo chown -R tenderer:tenderer /opt/tender-engine
sudo chmod -R u=rwX,g=rX,o= /opt/tender-engine
```

### 3.4 Set up Python environment

```bash
cd /opt/tender-engine
sudo -u tenderer python3.11 -m venv venv
sudo -u tenderer venv/bin/pip install --upgrade pip
sudo -u tenderer venv/bin/pip install -r requirements.txt
```

### 3.5 Create log directory

```bash
sudo mkdir -p /var/log/tender-engine
sudo chown tenderer:tenderer /var/log/tender-engine
sudo chmod 750 /var/log/tender-engine
```

### 3.6 Create secrets directory

```bash
sudo mkdir -p /etc/tender-engine
sudo chown tenderer:tenderer /etc/tender-engine
sudo chmod 700 /etc/tender-engine
```

---

## 4. CONFIGURATION FILES

### 4.1 Production `.env` at `/etc/tender-engine/.env`

```bash
# Save as /etc/tender-engine/.env with 0600 permissions
# Do NOT commit this file to git; generate it locally

# === Required: Discord webhook
TENDER_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN

# === Optional: Tuning parameters (defaults shown)
TENDER_MIN_SCORE=20
TENDER_SHORTLIST_N=10
TENDER_NOTIFY_N=5
TENDER_DECISION_BID_MIN_SCORE=40
TENDER_DECISION_REVIEW_MIN_SCORE=28
TENDER_DECISION_SME_VALUE_MAX=5000000
TENDER_DECISION_INCLUDE=BID,REVIEW
TENDER_RAW_RETENTION_DAYS=7

# === Internal: Base directory (do not change)
TENDER_BASE_DIR=/opt/tender-engine
```

**Setup command:**
```bash
sudo bash -c 'cat > /etc/tender-engine/.env' <<'EOF'
TENDER_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
TENDER_MIN_SCORE=20
TENDER_SHORTLIST_N=10
TENDER_NOTIFY_N=5
TENDER_DECISION_BID_MIN_SCORE=40
TENDER_DECISION_REVIEW_MIN_SCORE=28
TENDER_DECISION_SME_VALUE_MAX=5000000
TENDER_DECISION_INCLUDE=BID,REVIEW
TENDER_RAW_RETENTION_DAYS=7
TENDER_BASE_DIR=/opt/tender-engine
EOF
sudo chmod 600 /etc/tender-engine/.env
sudo chown tenderer:tenderer /etc/tender-engine/.env
```

### 4.2 Systemd service file at `/etc/systemd/system/tender-engine.service`

```ini
[Unit]
Description=ProcessEd Tender Engine Pipeline
Documentation=https://github.com/bilal-li/tender-engine
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=tenderer
Group=tenderer
WorkingDirectory=/opt/tender-engine

# Load secrets
EnvironmentFile=/etc/tender-engine/.env

# Python venv
ExecStart=/opt/tender-engine/venv/bin/python run_pipeline.py

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tender-engine

# Safety
TimeoutStartSec=300
TimeoutStopSec=30
Restart=no

[Install]
WantedBy=multi-user.target
```

**Setup command:**
```bash
sudo bash -c 'cat > /etc/systemd/system/tender-engine.service' <<'EOF'
[Unit]
Description=ProcessEd Tender Engine Pipeline
Documentation=https://github.com/bilal-li/tender-engine
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=tenderer
Group=tenderer
WorkingDirectory=/opt/tender-engine
EnvironmentFile=/etc/tender-engine/.env
ExecStart=/opt/tender-engine/venv/bin/python run_pipeline.py
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tender-engine
TimeoutStartSec=300
TimeoutStopSec=30
Restart=no

[Install]
WantedBy=multi-user.target
EOF
```

### 4.3 Systemd timer file at `/etc/systemd/system/tender-engine.timer`

```ini
[Unit]
Description=ProcessEd Tender Engine Daily Run
Documentation=https://github.com/bilal-li/tender-engine
Requires=tender-engine.service

[Timer]
# Run at 09:00 UTC daily
OnCalendar=*-*-* 09:00:00
Persistent=true
AccuracySec=1min

# Randomize start time ±5min to avoid API burst
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF
```

**Setup command:**
```bash
sudo bash -c 'cat > /etc/systemd/system/tender-engine.timer' <<'EOF'
[Unit]
Description=ProcessEd Tender Engine Daily Run
Documentation=https://github.com/bilal-li/tender-engine
Requires=tender-engine.service

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
AccuracySec=1min
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF
```

### 4.4 Logrotate config at `/etc/logrotate.d/tender-engine`

```logrotate
/var/log/tender-engine/*.log {
  daily
  rotate 30
  compress
  delaycompress
  notifempty
  create 0640 tenderer tenderer
  sharedscripts
  postrotate
    /bin/systemctl reload-or-restart rsyslog > /dev/null 2>&1 || true
  endscript
}
```

**Setup command:**
```bash
sudo bash -c 'cat > /etc/logrotate.d/tender-engine' <<'EOF'
/var/log/tender-engine/*.log {
  daily
  rotate 30
  compress
  delaycompress
  notifempty
  create 0640 tenderer tenderer
  sharedscripts
  postrotate
    /bin/systemctl reload-or-restart rsyslog > /dev/null 2>&1 || true
  endscript
}
EOF
```

---

## 5. COMPLETE DEPLOYMENT SCRIPT

Save as `deploy_hetzner.sh` and run with `bash deploy_hetzner.sh`:

```bash
#!/bin/bash
set -e
set -o pipefail

echo "[1/6] Installing system packages..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev build-essential git curl jq

echo "[2/6] Creating tenderer user..."
sudo useradd -m -s /bin/bash -d /home/tenderer tenderer || true

echo "[3/6] Cloning repository..."
cd /opt
if [ -d tender-engine ]; then
  echo "tender-engine already exists, updating..."
  cd tender-engine
  sudo -u tenderer git fetch origin
  sudo -u tenderer git reset --hard origin/main
else
  sudo git clone https://github.com/bilal-li/tender-engine.git tender-engine
  sudo chown -R tenderer:tenderer /opt/tender-engine
fi
cd /opt/tender-engine

echo "[4/6] Setting up Python environment..."
sudo -u tenderer python3.11 -m venv venv
sudo -u tenderer venv/bin/pip install --upgrade pip
sudo -u tenderer venv/bin/pip install -r requirements.txt

echo "[5/6] Creating logs and secrets directories..."
sudo mkdir -p /var/log/tender-engine
sudo chown tenderer:tenderer /var/log/tender-engine
sudo chmod 750 /var/log/tender-engine

sudo mkdir -p /etc/tender-engine
sudo chown tenderer:tenderer /etc/tender-engine
sudo chmod 700 /etc/tender-engine

echo "[6/6] Installing systemd files..."
sudo bash -c 'cat > /etc/systemd/system/tender-engine.service' <<'SVCEOF'
[Unit]
Description=ProcessEd Tender Engine Pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=tenderer
Group=tenderer
WorkingDirectory=/opt/tender-engine
EnvironmentFile=/etc/tender-engine/.env
ExecStart=/opt/tender-engine/venv/bin/python run_pipeline.py
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tender-engine
TimeoutStartSec=300
Restart=no

[Install]
WantedBy=multi-user.target
SVCEOF

sudo bash -c 'cat > /etc/systemd/system/tender-engine.timer' <<'TMREOF'
[Unit]
Description=ProcessEd Tender Engine Daily Run
Requires=tender-engine.service

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
AccuracySec=1min
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
TMREOF

sudo bash -c 'cat > /etc/logrotate.d/tender-engine' <<'LREOF'
/var/log/tender-engine/*.log {
  daily
  rotate 30
  compress
  delaycompress
  notifempty
  create 0640 tenderer tenderer
  sharedscripts
}
LREOF

echo ""
echo "✅ Installation complete!"
echo ""
echo "NEXT STEPS:"
echo "1. Set up Discord webhook:"
echo "   sudo nano /etc/tender-engine/.env"
echo "   # Replace YOUR_WEBHOOK_ID and YOUR_WEBHOOK_TOKEN"
echo ""
echo "2. Enable and start the timer:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable tender-engine.timer"
echo "   sudo systemctl start tender-engine.timer"
echo ""
echo "3. Verify:"
echo "   sudo systemctl status tender-engine.timer"
echo "   sudo systemctl list-timers tender-engine.timer"
echo ""
```

---

## 6. INITIAL SETUP (Run once)

### 6.1 Download and configure

```bash
# On your local machine, get the Discord webhook
# From Discord server settings → Webhooks → Create/copy URL

# On Hetzner server:
bash deploy_hetzner.sh

# Edit secrets
sudo nano /etc/tender-engine/.env
# Set TENDER_WEBHOOK_URL to your Discord webhook

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable tender-engine.timer
sudo systemctl start tender-engine.timer
```

### 6.2 Verify timer is active

```bash
sudo systemctl status tender-engine.timer
sudo systemctl list-timers tender-engine.timer
```

Expected output:
```
NEXT                         LEFT     LAST                         PASSED  UNIT                 ACTIVATES
Wed 2026-04-15 09:00:00 UTC  8h left  Tue 2026-04-14 09:00:32 UTC  45min ago tender-engine.timer tender-engine.service
```

---

## 7. RUN/ROLLBACK PROCEDURES

### 7.1 Manual trigger (on-demand run)

```bash
# Dry run (no side effects)
sudo systemctl start tender-engine.service --no-block
sudo journalctl -u tender-engine.service -f

# Check manifest
sudo -u tenderer cat /opt/tender-engine/data/runs/LATEST/run_manifest.json | jq '.'
```

### 7.2 Rollback (disable timer, keep data)

```bash
# Stop the timer
sudo systemctl stop tender-engine.timer

# Keep the service available for manual inspection
sudo systemctl status tender-engine.service

# Verify it's stopped
sudo systemctl list-timers
# Should NOT show tender-engine.timer
```

### 7.3 Re-enable after rollback

```bash
sudo systemctl start tender-engine.timer
sudo systemctl list-timers tender-engine.timer
```

---

## 8. HEALTH-CHECK PROCEDURES

### 8.1 Timer status

```bash
sudo systemctl status tender-engine.timer
sudo systemctl list-timers tender-engine.timer
sudo systemctl is-enabled tender-engine.timer  # Should output "enabled"
```

### 8.2 Latest run status

```bash
# Tail logs
sudo journalctl -u tender-engine.service -n 50 -f

# Parse latest manifest
LATEST=$(sudo ls -1 /opt/tender-engine/data/runs | sort | tail -1)
sudo -u tenderer cat /opt/tender-engine/data/runs/$LATEST/run_manifest.json | jq '{
  run_id: .run_id,
  status: .status,
  ingest_total_count: .ingest_total_count,
  shortlist_count: .shortlist_count,
  new_count: .new_count,
  notify_status: .steps.notify.status,
  duration_s: .total_duration_s
}'
```

### 8.3 Disk space

```bash
# Check logs
du -sh /var/log/tender-engine

# Check run artifacts
du -sh /opt/tender-engine/data/runs

# Check cleanup is working (should be removing 7+ day-old files)
sudo journalctl -u tender-engine.service | grep "removed.*old"
```

### 8.4 Python environment

```bash
# Verify venv
/opt/tender-engine/venv/bin/python --version
/opt/tender-engine/venv/bin/python -c "import requests; print('requests OK')"
```

---

## 9. DISCORD 405 TROUBLESHOOTING

**Symptom:** Logs show `Discord webhook rejected (HTTP 405)`

### 9.1 Cause analysis

405 = "Method Not Allowed" — usually means:
- Webhook URL is incorrect (points to wrong endpoint)
- Webhook was deleted or rotated
- URL malformed or incomplete

### 9.2 Diagnostic steps

```bash
# 1. Check webhook is set
sudo cat /etc/tender-engine/.env | grep TENDER_WEBHOOK_URL

# 2. Validate format
sudo -u tenderer python3 <<'PYEOF'
import os
url = os.getenv("TENDER_WEBHOOK_URL", "").strip()
if url.startswith("https://discord.com/api/webhooks/"):
    print("✅ Webhook format looks valid")
else:
    print("❌ Webhook format invalid")
    print("   Expected: https://discord.com/api/webhooks/<ID>/<TOKEN>")
    print("   Got:", url[:50] + "..." if len(url) > 50 else url)
PYEOF

# 3. Test connectivity (curl)
WEBHOOK=$(sudo cat /etc/tender-engine/.env | grep TENDER_WEBHOOK_URL | cut -d= -f2-)
curl -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"content":"Hetzner test from $(hostname) at $(date)"}' \
  -v 2>&1 | grep -E "(HTTP|error|405)"
```

### 9.3 Fix

```bash
# 1. Get fresh webhook from Discord
# Discord → Server Settings → Integrations → Webhooks → Create New Webhook
# Copy the full URL

# 2. Update on Hetzner
sudo bash -c 'cat > /etc/tender-engine/.env' <<'EOF'
TENDER_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_NEW_WEBHOOK_ID/YOUR_NEW_TOKEN
# ... rest of vars ...
EOF
sudo chmod 600 /etc/tender-engine/.env

# 3. Test
sudo systemctl start tender-engine.service
sudo journalctl -u tender-engine.service -f | grep -i discord
```

---

## 10. LOG LOCATIONS

| What | Where | Rotate |
|------|-------|--------|
| Systemd journal | `journalctl -u tender-engine.service -f` | automatic (systemd) |
| Run artifacts | `/opt/tender-engine/data/runs/YYYY-MM-DD_HHMMSS/` | 7 days (retention policy) |
| Run manifests | `/opt/tender-engine/data/runs/*/run_manifest.json` | per-run (kept 7 days) |
| Python errors | Journal (see above) | — |

**View recent runs:**
```bash
ls -lh /opt/tender-engine/data/runs/ | tail -20

# Latest manifest summary
LATEST=$(ls -1 /opt/tender-engine/data/runs | sort | tail -1)
jq '.status, .new_count, .steps.notify.status' /opt/tender-engine/data/runs/$LATEST/run_manifest.json
```

---

## 11. VALIDATION CHECKLIST

Run through this after deployment:

- [ ] User `tenderer` exists: `id tenderer`
- [ ] Python venv works: `/opt/tender-engine/venv/bin/python --version`
- [ ] Systemd files loaded: `sudo systemctl daemon-reload && sudo systemctl list-unit-files | grep tender`
- [ ] Timer enabled: `sudo systemctl is-enabled tender-engine.timer`
- [ ] Timer active: `sudo systemctl is-active tender-engine.timer`
- [ ] Secrets protected: `ls -la /etc/tender-engine/.env` (should show `-rw------- tenderer tenderer`)
- [ ] Next run scheduled: `sudo systemctl list-timers tender-engine.timer`
- [ ] Manual test passes: `sudo systemctl start tender-engine.service && sleep 30 && journalctl -u tender-engine.service | tail -5`
- [ ] Manifest created: `ls -la /opt/tender-engine/data/runs/`
- [ ] Discord webhook test: `curl -X POST "${WEBHOOK}" -H "Content-Type: application/json" -d '{"content":"test"}'`

---

## 12. OPEN RISKS & MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Discord webhook rotated** | Notifications fail silently; run continues | Health check job queries manifest weekly; ops alerted if `notify.status != ok` for 3+ runs |
| **API rate limiting (FTS/CF)** | Ingest returns 0 records; shortlist empty | Exponential backoff + jitter in scraper; logs warn if <50 records ingested |
| **Disk fills with old runs** | Pipeline fails on write; no new manifests | Retention policy auto-deletes 7+ day files; logrotate caps at 30 rotations |
| **systemd timer misconfigured** | Runs never trigger (or double-trigger) | `systemctl list-timers` checked weekly; logs monitored for duplicate run_ids |
| **Python dependency breaks** | Ingest fails immediately | Requirements pinned; venv recreated at deploy time; test import on each run |
| **Secrets leaked in logs** | Webhook URL exposed in journal | No secrets passed as args; webhook URL never printed; logs only show "configured (masked)" |

---

## 13. MONITORING & ALERTS (Future)

Recommended additions for production:

1. **Weekly health check script** (run via cron)
   ```bash
   # Check last 7 runs for notify failures
   # Alert on 3+ consecutive failures
   ```

2. **Discord channel for ops**
   - Create second webhook for ops notifications
   - Send status: "Last run: $RUN_ID, status: $STATUS, new: $COUNT"
   - Send alerts on failures

3. **Sentry/DataDog integration** (optional)
   - Forward logs to external monitoring
   - Alert on regex matches (405 error, permission denied, etc.)

---

## 14. QUICK REFERENCE

**Start/stop the timer:**
```bash
sudo systemctl start tender-engine.timer     # Enable daily runs
sudo systemctl stop tender-engine.timer      # Disable daily runs
sudo systemctl restart tender-engine.timer   # Restart (runs immediately)
```

**Manual run:**
```bash
sudo systemctl start tender-engine.service --no-block
journalctl -u tender-engine.service -f
```

**View config:**
```bash
sudo cat /etc/tender-engine/.env          # Check secrets are loaded
sudo systemctl cat tender-engine.service  # View service file
```

**Upgrade code:**
```bash
cd /opt/tender-engine
sudo -u tenderer git fetch origin
sudo -u tenderer git reset --hard origin/main
sudo -u tenderer venv/bin/pip install -r requirements.txt
sudo systemctl restart tender-engine.timer  # Restart with new code
```

**Destroy and rebuild:**
```bash
sudo systemctl disable tender-engine.timer tender-engine.service
sudo rm -rf /opt/tender-engine /etc/tender-engine /var/log/tender-engine
bash deploy_hetzner.sh  # Re-run full deployment
```

---

## END OF DEPLOYMENT DOCUMENT

**Questions?** Contact: bilal@processedconstruction.co.uk  
**Repository:** https://github.com/bilal-li/tender-engine  
**Last Updated:** April 2026
