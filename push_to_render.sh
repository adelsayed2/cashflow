#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# We need the remote URL. If it's commented out in .env, we'll try to find it.
# Look for the line that was previously DATABASE_URL (the render one)
REMOTE_URL=$(grep "render.com" .env | head -n 1 | sed -E 's/^.*DATABASE_URL=//')

if [ -z "$REMOTE_URL" ]; then
    echo "❌ Error: Remote Database URL not found in .env."
    exit 1
fi

# Add sslmode=require if missing
if [[ "$REMOTE_URL" != *"sslmode"* ]]; then
    if [[ "$REMOTE_URL" == *"?"* ]]; then
        REMOTE_URL="${REMOTE_URL}&sslmode=require"
    else
        REMOTE_URL="${REMOTE_URL}?sslmode=require"
    fi
fi

echo "⚠️  WARNING: This will OVERWRITE the production database on Render with your local Docker data."
echo "Remote Host: $(echo $REMOTE_URL | cut -d@ -f2 | cut -d/ -f1)"
read -p "Are you sure you want to proceed? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Push cancelled."
    exit 1
fi

echo "🚀 Starting push to Render..."

# 1. Dump local database from Docker
# We use --clean and --if-exists to make the restore easier
echo "📦 Dumping local data..."
docker exec cashflow-db pg_dump -U cashflow_user -d cashflow_local --clean --if-exists --no-owner --no-privileges > local_dump.sql

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to dump local database."
    rm -f local_dump.sql
    exit 1
fi

# 2. Upload to Render
# We use the psql client inside the Docker container since it's already installed there
echo "📤 Uploading to Render via Docker container (this may take a moment)..."
cat local_dump.sql | docker exec -i cashflow-db psql "$REMOTE_URL"

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to upload to Render. Check your internet connection and IP whitelisting."
    rm -f local_dump.sql
    exit 1
fi

echo "✅ Success! Production has been updated."
rm -f local_dump.sql
