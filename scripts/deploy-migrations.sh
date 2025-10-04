#!/bin/bash

# 🚀 ENTERPRISE DJANGO MIGRATIONS DEPLOYMENT SCRIPT
# Tuki Platform - Professional Migration Management

set -e  # Exit on any error

# Configuration
PROJECT_ID="tukiprod"
REGION="us-central1"
ARTIFACT_REGISTRY="us-central1-docker.pkg.dev/tukiprod/tuki-repo"
MIGRATION_IMAGE="tuki-migrate:latest"
JOB_NAME="tuki-migrate-job"

echo "🏗️  ENTERPRISE MIGRATION DEPLOYMENT STARTING..."
echo "📋 Project: $PROJECT_ID"
echo "🌍 Region: $REGION"
echo "📦 Image: $ARTIFACT_REGISTRY/$MIGRATION_IMAGE"

# Step 1: Build migration image
echo ""
echo "🔨 STEP 1: Building migration image..."
gcloud builds submit --config cloudbuild-migrate.yaml

# Step 2: Delete existing job if it exists
echo ""
echo "🗑️  STEP 2: Cleaning up existing migration job..."
gcloud run jobs delete $JOB_NAME --region=$REGION --quiet || echo "No existing job to delete"

# Step 3: Create new migration job
echo ""
echo "⚙️  STEP 3: Creating migration job..."
gcloud run jobs create $JOB_NAME \
  --image $ARTIFACT_REGISTRY/$MIGRATION_IMAGE \
  --region $REGION \
  --env-vars-file migrate-env.yaml \
  --max-retries=1 \
  --parallelism=1 \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=900 \
  --set-cloudsql-instances=tukiprod:us-central1:tuki-db-prod

echo ""
echo "✅ Migration job created successfully!"

# Step 4: Execute migration job
echo ""
echo "🚀 STEP 4: Executing migrations..."
gcloud run jobs execute $JOB_NAME --region=$REGION --wait

# Step 5: Verify migration success
echo ""
echo "🔍 STEP 5: Verifying migration results..."
EXECUTION_NAME=$(gcloud run jobs executions list --job=$JOB_NAME --region=$REGION --limit=1 --format="value(metadata.name)")

if [ -n "$EXECUTION_NAME" ]; then
    echo "📊 Latest execution: $EXECUTION_NAME"
    
    # Get execution status
    STATUS=$(gcloud run jobs executions describe $EXECUTION_NAME --region=$REGION --format="value(status.conditions[0].type)")
    
    if [ "$STATUS" = "Completed" ]; then
        echo "✅ MIGRATION COMPLETED SUCCESSFULLY!"
        echo ""
        echo "🎉 ENTERPRISE MIGRATION DEPLOYMENT COMPLETED!"
        echo "🔗 View logs: https://console.cloud.google.com/run/jobs/executions/details/$REGION/$EXECUTION_NAME/tasks?project=$PROJECT_ID"
    else
        echo "❌ MIGRATION FAILED!"
        echo "📋 Execution status: $STATUS"
        exit 1
    fi
else
    echo "❌ Could not find execution details"
    exit 1
fi

echo ""
echo "🏆 DEPLOYMENT SUMMARY:"
echo "   ✅ Migration image built and pushed"
echo "   ✅ Migration job created"
echo "   ✅ Migrations executed successfully"
echo "   ✅ Database schema updated"
echo ""
echo "🚀 Ready for production deployment!"
