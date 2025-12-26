# Making This Repository Public - Security Checklist

This repository contains examples and templates for a Raspberry Pi home automation infrastructure. Use this checklist to ensure sensitive information is not exposed when sharing publicly.

## Automated Protection

The repository includes automated protection mechanisms:

### 1. Git Hooks
Run `./scripts/setup-git-hooks.sh` to install pre-commit hooks that block:
- `.env` files with real secrets
- Files matching secret patterns (API keys, tokens, passwords)
- Real network topology files (`prometheus/prometheus.yml`, `.github/copilot-instructions.md`)
- Invalid `prometheus/influxdb3_token` (must be placeholder)

### 2. .gitignore Protection
The following files are automatically excluded from commits:
```
.env
*.env (except .env.example)
/prometheus/prometheus.yml
/.github/copilot-instructions.md
```

## Network Topology Sanitization

**IMPORTANT**: This repository uses `.example` templates for configs containing network information.

### Files with Network Topology

| File | Status | Public Version |
|------|--------|----------------|
| `prometheus/prometheus.yml` | **Gitignored** | `prometheus/prometheus.yml.example` |
| `.github/copilot-instructions.md` | **Gitignored** | `.github/copilot-instructions.md.example` |

### Setting Up Local Configs

After cloning this repo, run:
```bash
./scripts/setup-local-configs.sh
```

This creates local versions with your actual:
- Pi hostnames (`raspberrypi.local`, `raspberrypi2.local`, etc.)
- IP addresses (if needed)
- Usernames

The script prompts for your values and generates working configs from the `.example` templates.

### Sanitization Patterns

When creating `.example` templates, use these placeholders:

| Real Value | Placeholder |
|------------|-------------|
| `raspberrypi.local` | `PI1_HOSTNAME` |
| `raspberrypi2.local` | `PI2_HOSTNAME` |
| `raspberrypi3.local` | `PI3_HOSTNAME` |
| `192.168.0.167` | `PI1_IP` or use hostname |
| `192.168.0.146` | `PI2_IP` or use hostname |
| `aachten` (username) | `USERNAME` |
| `//192.168.0.1/share` (NAS) | `//NAS_IP/SHARE_NAME` |
| Grafana Cloud URL | `https://USERNAME.grafana.net` |
| GitHub repo URLs | `https://github.com/USERNAME/repo.git` |

## Secrets Audit

### Files That MUST Be Excluded
- [x] `.env` - Contains all real API keys, tokens, passwords
- [x] `prometheus/influxdb3_token` - Real token (only placeholder committed)
- [x] `prometheus/prometheus.yml` - Contains real network topology
- [x] `.github/copilot-instructions.md` - Contains real network details

### Files Safe to Commit
- [x] `.env.example` - Template with placeholder values
- [x] `prometheus/prometheus.yml.example` - Sanitized template
- [x] `.github/copilot-instructions.md.example` - Sanitized template
- [x] `docker-compose.yml` - No secrets (uses env vars)
- [x] All scripts in `scripts/` - Use env vars, no hardcoded secrets
- [x] Grafana dashboards `grafana/dashboards-cloud/*.json` - No secrets
- [x] Nginx configs `nginx-proxy-manager/data/nginx/proxy_host/*.conf` - Public configs

## Pre-Publish Verification

Before making repository public or pushing sensitive changes:

1. **Run git hooks setup**:
   ```bash
   ./scripts/setup-git-hooks.sh
   ```

2. **Test pre-commit protection**:
   ```bash
   # Try to stage blocked file (should fail)
   git add prometheus/prometheus.yml
   git commit -m "test"
   ```

3. **Verify .gitignore**:
   ```bash
   git status --ignored | grep -E '(\.env|prometheus\.yml|copilot-instructions\.md)'
   ```

4. **Search for real IPs/hostnames** in tracked files:
   ```bash
   git grep -E '192\.168\.[0-9]+\.[0-9]+|raspberrypi[0-9]?\.local' -- ':!*.md' ':!*.example'
   ```

5. **Check for accidental secrets**:
   ```bash
   git log -p | grep -i 'password\|secret\|api_key' | grep -v example
   ```

## If Sensitive Data Was Committed

If you accidentally committed sensitive information:

### Option 1: Rewrite Recent Commits (if not pushed)
```bash
# Remove file from last commit
git rm --cached <file>
git commit --amend --no-edit

# Remove from last N commits
git filter-branch --tree-filter 'rm -f <file>' HEAD~N..HEAD
```

### Option 2: Use git-filter-repo (recommended for pushed commits)
```bash
# Install git-filter-repo
pip install git-filter-repo

# Remove file from entire history
git filter-repo --path <file> --invert-paths

# Force push (WARNING: rewrites history)
git push --force-with-lease
```

### Option 3: Nuclear Option - Delete & Recreate
If sensitive data is widespread:
1. Delete GitHub repository
2. Create clean version with proper .gitignore and templates
3. Recreate repository from scratch

## Post-Publication Monitoring

After making public:

1. **GitHub Secret Scanning**: Monitor "Security" tab for detected secrets
2. **Review Pull Requests**: Ensure contributors don't commit secrets
3. **Document for Contributors**: Link to this checklist in `CONTRIBUTING.md`

## Quick Reference

### Safe Workflow
```bash
# 1. Clone repo
git clone https://github.com/USERNAME/raspberry-pi-docker.git
cd raspberry-pi-docker

# 2. Setup git hooks
./scripts/setup-git-hooks.sh

# 3. Create .env from template
cp .env.example .env
# Edit .env with your secrets

# 4. Setup local configs
./scripts/setup-local-configs.sh
# Follow prompts for your network

# 5. Work normally - hooks protect you
git add .
git commit -m "feat: my changes"
# Hooks will block any sensitive files
```

### Maintaining Templates

When updating configs with network info:

```bash
# 1. Update your local file
vim prometheus/prometheus.yml

# 2. Test it works
docker compose restart prometheus

# 3. Sanitize and update template
sed -e 's/raspberrypi2.local/PI2_HOSTNAME/g' \
    -e 's/192.168.0.146/PI2_IP/g' \
    prometheus/prometheus.yml > prometheus/prometheus.yml.example

# 4. Commit only the template
git add prometheus/prometheus.yml.example
git commit -m "docs: update prometheus config template"
```

## Support

Questions about sanitization? See:
- `.github/copilot-instructions.md.example` for configuration documentation
- `scripts/setup-local-configs.sh` for automated setup
- `scripts/setup-git-hooks.sh` for hook protection
