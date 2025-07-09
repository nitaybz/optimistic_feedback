#!/bin/bash

# Local validation script for Home Assistant integrations
# This runs the same validations as the GitHub Actions

echo "🔍 Running local Home Assistant validation..."

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed. Please install Docker first."
    exit 1
fi

echo "📦 Running Hassfest validation..."

# Run hassfest validation using Home Assistant's validation container
docker run --rm \
    -v "$(pwd)":/github/workspace \
    ghcr.io/home-assistant/hass-action:latest \
    python -m homeassistant.scripts.hassfest \
    --action validate \
    --integration-path /github/workspace/custom_components

echo "✅ Hassfest validation complete!"

echo "🔍 Running HACS validation..."

# Run HACS validation
docker run --rm \
    -e INPUT_CATEGORY=integration \
    -v "$(pwd)":/github/workspace \
    ghcr.io/hacs/action:main

echo "✅ All validations complete!"
