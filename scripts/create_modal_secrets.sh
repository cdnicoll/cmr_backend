#!/bin/bash
# Create Modal secrets for deployment.
# Prerequisites: modal setup, MODAL_PROJECT in .env (e.g. cody-99083)
# Workers require: supabase-credentials-{ENV}, app-config-{ENV}
set -e
PROJECT_ARG=""
[ -n "$MODAL_PROJECT" ] && PROJECT_ARG="-e $MODAL_PROJECT"

echo "Create Modal secrets. Source .env first: source .env  # or export vars"
echo ""
echo "Develop (deploy_dev):"
echo "  modal secret create $PROJECT_ARG supabase-credentials-develop SUPABASE_URL=\$SUPABASE_URL SUPABASE_PUBLISHABLE_KEY=\$SUPABASE_PUBLISHABLE_KEY SUPABASE_SECRET_KEY=\$SUPABASE_SECRET_KEY TRANSACTION_POOLER_URL=\$TRANSACTION_POOLER_URL"
echo "  modal secret create $PROJECT_ARG app-config-develop ENVIRONMENT=develop SCRAPE_STUCK_TIMEOUT_MINUTES=15 INGEST_STUCK_TIMEOUT_MINUTES=30 SCRAPING_PROXY_URL=\$SCRAPING_PROXY_URL ..."
echo ""
echo "Production (deploy_prod):"
echo "  modal secret create $PROJECT_ARG supabase-credentials-production SUPABASE_URL=... SUPABASE_SECRET_KEY=... TRANSACTION_POOLER_URL=..."
echo "  modal secret create $PROJECT_ARG app-config-production ENVIRONMENT=production SCRAPE_STUCK_TIMEOUT_MINUTES=15 INGEST_STUCK_TIMEOUT_MINUTES=30 ..."
