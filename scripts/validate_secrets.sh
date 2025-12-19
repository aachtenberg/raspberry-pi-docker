#!/bin/bash
# Script to validate .env configuration before deploying Docker stack

set -e

ENV_FILE=".env"
EXAMPLE_FILE=".env.example"

echo "🔍 Validating Docker secrets configuration..."
echo ""

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: $ENV_FILE not found"
    echo ""
    echo "Please create it from the template:"
    echo "  cp $EXAMPLE_FILE $ENV_FILE"
    echo "  vim $ENV_FILE"
    echo ""
    exit 1
fi

echo "✅ $ENV_FILE exists"

# Check if .env is in .gitignore
if git check-ignore -q "$ENV_FILE" 2>/dev/null; then
    echo "✅ $ENV_FILE is properly gitignored"
else
    echo "⚠️  Warning: $ENV_FILE is NOT gitignored (may be committed!)"
fi

# Check for placeholder values
PLACEHOLDERS=$(grep -o 'YOUR_[A-Z_]*' "$ENV_FILE" 2>/dev/null || true)
if [ -n "$PLACEHOLDERS" ]; then
    echo "❌ Found placeholder values that need to be replaced:"
    echo "$PLACEHOLDERS" | sort -u | sed 's/^/   - /'
    echo ""
    echo "Please edit $ENV_FILE and replace all YOUR_* placeholders"
    exit 1
fi

echo "✅ No placeholder values found (YOUR_*)"

# Check required variables
REQUIRED_VARS=("CLOUDFLARE_TUNNEL_TOKEN" "INFLUXDB_ADMIN_PASSWORD" "INFLUXDB_ORG_ID" "INFLUXDB_ADMIN_TOKEN")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^$var=" "$ENV_FILE"; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "❌ Missing required variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    exit 1
fi

echo "✅ All required variables present"

# Check InfluxDB token length (should be ~88 chars)
TOKEN_LENGTH=$(grep '^INFLUXDB_ADMIN_TOKEN=' "$ENV_FILE" | cut -d'=' -f2 | wc -c)
if [ "$TOKEN_LENGTH" -gt 20 ]; then
    echo "✅ InfluxDB token length: $TOKEN_LENGTH characters (looks valid)"
else
    echo "⚠️  InfluxDB token seems too short ($TOKEN_LENGTH chars). Verify it's correct."
fi

# Check InfluxDB org ID format (16-char hex)
ORG_ID=$(grep '^INFLUXDB_ORG_ID=' "$ENV_FILE" | cut -d'=' -f2)
if [[ $ORG_ID =~ ^[0-9a-f]{16}$ ]]; then
    echo "✅ InfluxDB Organization ID format looks valid"
else
    echo "⚠️  InfluxDB Organization ID may be incorrect (should be 16-char hex)"
fi

# Validate docker-compose.yml syntax
if command -v docker &> /dev/null; then
    if docker compose config > /dev/null 2>&1; then
        echo "✅ docker-compose.yml syntax is valid"
    else
        echo "❌ docker-compose.yml has syntax errors"
        exit 1
    fi
else
    echo "⚠️  Docker not found, skipping compose validation"
fi

echo ""
echo "✅ Configuration looks good!"
echo ""
echo "Next steps:"
echo "  1. Review changes: docker compose config"
echo "  2. Start services: docker compose up -d"
echo "  3. Check logs: docker compose logs -f"

# Additional repo-level checks (no secrets committed)
echo ""
echo "🔒 Running repository secret checks..."

# 1) prometheus/influxdb3_token must be placeholder
if [ -f prometheus/influxdb3_token ]; then
    CONTENT=$(cat prometheus/influxdb3_token)
    if [ "$CONTENT" != "INFLUXDB3_TOKEN_PLACEHOLDER" ]; then
        echo "❌ ERROR: prometheus/influxdb3_token contains non-placeholder content"
        echo "   Replace with INFLUXDB3_TOKEN_PLACEHOLDER before committing."
        exit 1
    fi
    echo "✅ prometheus/influxdb3_token is placeholder"
fi

# 2) Scan staged diffs for common secret patterns
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git diff --cached | grep -E '(password|secret|api_key|token).*=.*[a-zA-Z0-9_-]{20,}|apiv3_[A-Za-z0-9_-]+' >/dev/null 2>&1; then
        echo "❌ ERROR: Staged changes include secret-like content"
        echo "   Unstage and remove secrets. Use .env for local configuration."
        exit 1
    fi
    echo "✅ No secret-like content found in staged changes"
fi
