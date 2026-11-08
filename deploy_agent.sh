#!/usr/bin/env bash
# Deploy (or update) the site assistant: CloudFormation stack + Lambda code, then write the
# function URL into agent.json so the site build embeds it.
#
#   ./deploy_agent.sh                     # uses defaults below
#   MODEL_ID=... ALLOWED_ORIGIN=https://agent-precog.org ./deploy_agent.sh
#
# Afterwards run ./deploy.sh to rebuild and publish the site with the panel wired up.
set -euo pipefail
cd "$(dirname "$0")"

SITE_STACK="${SITE_STACK:-agent-precog}"
STACK="${AGENT_STACK:-${SITE_STACK}-agent}"
REGION="${AWS_REGION:-eu-west-2}"
SITE_NAME="${SITE_NAME:-agent-precog.org}"
SITE_URL="${SITE_URL:-https://agent-precog.org}"
ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-$SITE_URL}"
DAILY_CAP="${DAILY_CAP:-300}"
LOG_QUESTIONS="${LOG_QUESTIONS:-true}"
ENABLED="${ENABLED:-true}"

BUCKET=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$SITE_STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)

# Default model: EU cross-region Claude Haiku 4.5. (Haiku 5.5 is account-gated on this account as of Nov 2026;
# set MODEL_ID=eu.anthropic.claude-haiku-5-5 once Bedrock allows it.)
MODEL_ID="${MODEL_ID:-eu.anthropic.claude-haiku-4-5-20251001-v1:0}"
echo "==> Model: $MODEL_ID   Bucket: $BUCKET   Origin: $ALLOWED_ORIGIN"

echo "==> Deploying stack $STACK"
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file infra/agent.yaml --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides SiteBucket="$BUCKET" SiteName="$SITE_NAME" SiteUrl="$SITE_URL" \
    AllowedOrigin="$ALLOWED_ORIGIN" ModelId="$MODEL_ID" DailyCap="$DAILY_CAP" LogQuestions="$LOG_QUESTIONS" Enabled="$ENABLED"

echo "==> Uploading function code"
rm -f /tmp/agent.zip && (cd agent && zip -q /tmp/agent.zip handler.py)
aws lambda update-function-code --region "$REGION" --function-name "$STACK" --zip-file fileb:///tmp/agent.zip --query LastUpdateStatus --output text
aws lambda wait function-updated --region "$REGION" --function-name "$STACK"

URL=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='AgentUrl'].OutputValue" --output text)
printf '{"url": "%s"}\n' "$URL" > agent.json
echo "==> Agent URL written to agent.json: $URL"

echo "==> Smoke test"
curl -s -X POST "$URL" -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"In one sentence, what is this site?"}]}' | head -c 600; echo
echo
echo "Now run ./deploy.sh to publish the site with the assistant enabled."
