#!/bin/bash
# Setup local network-specific configurations from sanitized templates
# This script creates local versions of configs with your actual hostnames/IPs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔧 Setting up local network configurations..."
echo ""

# Function to prompt for value with default
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local result

    read -p "$prompt [$default]: " result
    echo "${result:-$default}"
}

# Check if local configs already exist
if [ -f "$PROJECT_ROOT/prometheus/prometheus.yml" ] && [ ! -L "$PROJECT_ROOT/prometheus/prometheus.yml" ]; then
    echo "⚠️  Local prometheus.yml already exists."
    read -p "Overwrite? (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Skipping prometheus.yml"
        SKIP_PROMETHEUS=1
    fi
fi

if [ -f "$PROJECT_ROOT/.github/copilot-instructions.md" ] && [ ! -L "$PROJECT_ROOT/.github/copilot-instructions.md" ]; then
    echo "⚠️  Local copilot-instructions.md already exists."
    read -p "Overwrite? (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Skipping copilot-instructions.md"
        SKIP_COPILOT=1
    fi
fi

echo ""
echo "📝 Enter your local network configuration:"
echo ""

# Gather configuration values
PI1_HOSTNAME=$(prompt_with_default "Pi 1 hostname" "raspberrypi.local")
PI2_HOSTNAME=$(prompt_with_default "Pi 2 hostname" "raspberrypi2.local")
PI3_HOSTNAME=$(prompt_with_default "Pi 3 hostname" "raspberrypi3.local")
USERNAME=$(prompt_with_default "SSH username" "$(whoami)")

echo ""
echo "🔨 Creating local configurations..."

# Create prometheus.yml from template
if [ -z "$SKIP_PROMETHEUS" ]; then
    sed -e "s/PI1_HOSTNAME/$PI1_HOSTNAME/g" \
        -e "s/PI2_HOSTNAME/$PI2_HOSTNAME/g" \
        "$PROJECT_ROOT/prometheus/prometheus.yml.example" > "$PROJECT_ROOT/prometheus/prometheus.yml"
    echo "✅ Created prometheus/prometheus.yml"
fi

# Create copilot-instructions.md from template
if [ -z "$SKIP_COPILOT" ]; then
    sed -e "s/PI1_HOSTNAME/$PI1_HOSTNAME/g" \
        -e "s/PI2_HOSTNAME/$PI2_HOSTNAME/g" \
        -e "s/PI3_HOSTNAME/$PI3_HOSTNAME/g" \
        -e "s/USERNAME/$USERNAME/g" \
        "$PROJECT_ROOT/.github/copilot-instructions.md.example" > "$PROJECT_ROOT/.github/copilot-instructions.md"
    echo "✅ Created .github/copilot-instructions.md"
fi

echo ""
echo "🎉 Local configuration setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Review the generated files:"
echo "      - prometheus/prometheus.yml"
echo "      - .github/copilot-instructions.md"
echo "   2. Restart Prometheus: docker compose restart prometheus"
echo "   3. These files are gitignored and won't be committed"
echo ""
echo "💡 Tip: Run './scripts/setup-git-hooks.sh' to ensure pre-commit protection"
