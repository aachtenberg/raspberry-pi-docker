#!/bin/bash
# ============================================================================
# Git Hooks Setup Script
# Sets up pre-commit and post-commit hooks for the raspberry-pi-docker project
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "🔧 Setting up Git hooks for raspberry-pi-docker..."
echo ""

if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "❌ Error: Not a git repository"
    exit 1
fi

# Create pre-commit hook
echo "📝 Creating pre-commit hook..."
cat > "$HOOKS_DIR/pre-commit" << 'HOOK'
#!/bin/bash
set -e
echo "🔍 Running pre-commit checks..."
echo ""

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

# Check 1: Prevent committing .env file
if echo "$STAGED_FILES" | grep -qE '^\.env$|/\.env$'; then
    echo "❌ ERROR: Attempting to commit .env file!"
    echo "   Please unstage it with: git reset HEAD .env"
    exit 1
fi
echo "✅ No .env file in staged changes"

# Check 2: Block common secret patterns in staged content (skip .example files)
BLOCKED_PATTERNS='(password|secret|api_key|token).*=.*[a-zA-Z0-9_-]{20,}|apiv3_[A-Za-z0-9_-]+'
for file in $STAGED_FILES; do
    # Skip .example files and documentation
    if [[ "$file" =~ \.example$ ]] || [[ "$file" =~ \.md$ ]]; then
        continue
    fi
    if [ -f "$file" ]; then
        if git diff --cached "$file" | grep -E "$BLOCKED_PATTERNS" > /dev/null 2>&1; then
            echo "❌ ERROR: Secret-like content detected in $file"
            echo "   Staged diff matches blocked patterns: $BLOCKED_PATTERNS"
            echo "   Please remove secrets and use .env or placeholders."
            exit 1
        fi
    fi
done
echo "✅ No blocked secret patterns detected"

# Check 2b: Ensure prometheus/influxdb3_token contains placeholder only
if echo "$STAGED_FILES" | grep -q '^prometheus/influxdb3_token$'; then
    TOKEN_CONTENT=$(git show :prometheus/influxdb3_token || true)
    if [ "$TOKEN_CONTENT" != "INFLUXDB3_TOKEN_PLACEHOLDER" ]; then
        echo "❌ ERROR: prometheus/influxdb3_token must contain INFLUXDB3_TOKEN_PLACEHOLDER"
        echo "   Do not commit real InfluxDB 3 tokens."
        exit 1
    fi
    echo "✅ prometheus/influxdb3_token is placeholder"
fi

# Check 3: Block real network topology configs (should use .example templates)
if echo "$STAGED_FILES" | grep -qE '^prometheus/prometheus\.yml$|^\.github/copilot-instructions\.md$'; then
    echo "❌ ERROR: Attempting to commit local network topology files!"
    echo "   These files contain sensitive network information (IPs/hostnames):"
    for file in prometheus/prometheus.yml .github/copilot-instructions.md; do
        if echo "$STAGED_FILES" | grep -q "^$file$"; then
            echo "   - $file"
        fi
    done
    echo ""
    echo "   📋 Solution:"
    echo "   1. Unstage with: git reset HEAD <file>"
    echo "   2. Commit sanitized .example templates instead"
    echo "   3. Run './scripts/setup-local-configs.sh' to regenerate local versions"
    exit 1
fi
echo "✅ No sensitive network topology files in staged changes"

# Check 3: Validate docker-compose.yml syntax
if echo "$STAGED_FILES" | grep -q 'docker-compose.yml'; then
    echo "🐳 Validating docker-compose.yml syntax..."
    if docker compose config -q 2>/dev/null; then
        echo "✅ docker-compose.yml syntax is valid"
    else
        echo "❌ ERROR: docker-compose.yml has syntax errors!"
        exit 1
    fi
fi

echo ""
echo "✅ All pre-commit checks passed!"
HOOK

chmod +x "$HOOKS_DIR/pre-commit"
echo "✅ pre-commit hook installed"

# Create post-commit hook
echo "📝 Creating post-commit hook..."
cat > "$HOOKS_DIR/post-commit" << 'HOOK'
#!/bin/bash
echo ""
echo "✅ Commit successful!"
BRANCH=$(git rev-parse --abbrev-ref HEAD)
UNPUSHED=$(git log origin/$BRANCH..$BRANCH --oneline 2>/dev/null | wc -l)
if [ "$UNPUSHED" -gt 0 ]; then
    echo "📤 Reminder: $UNPUSHED unpushed commit(s) - git push origin $BRANCH"
fi
HOOK

chmod +x "$HOOKS_DIR/post-commit"
echo "✅ post-commit hook installed"

echo ""
echo "🎉 Git hooks setup complete!"
echo "   - pre-commit: Blocks .env, secrets, network topology, validates docker compose"
echo "   - post-commit: Push reminder"
