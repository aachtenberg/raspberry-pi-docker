#!/bin/bash
# Initialize InfluxDB 3 Core admin token on first deployment
# This script is called manually after first container startup
# Token is then saved to .env and reused across deployments

set -e

echo "InfluxDB 3 Core Token Setup"
echo "============================"
echo ""
echo "To generate an admin token, run:"
echo "  docker compose exec influxdb3-core influxdb3 create token --admin"
echo ""
echo "Then save the token to .env as:"
echo "  INFLUXDB3_ADMIN_TOKEN=<token-value>"
echo ""
echo "For automated setup, use the deploy script from:"
echo "  https://github.com/aachtenberg/influxdbv3-core"

