#!/usr/bin/env bash
# Build the site and deploy it to AWS (S3 + CloudFront) in one command.
#
#   ./deploy.sh                       # first run creates the stack; later runs update + sync
#   DOMAIN=agent-precog.ai CERT_ARN=arn:aws:acm:us-east-1:...:certificate/... ZONE_ID=Z... ./deploy.sh
#
# Requires: aws CLI v2 configured (aws configure / SSO), python3 with jinja2.
# Region for the stack can be anything; the ACM certificate MUST be in us-east-1.
set -euo pipefail

STACK="${STACK:-agent-precog}"
REGION="${AWS_REGION:-eu-west-2}"
DOMAIN="${DOMAIN:-}"
CERT_ARN="${CERT_ARN:-}"
ZONE_ID="${ZONE_ID:-}"

cd "$(dirname "$0")"

echo "==> Building site"
python3 build.py --out site
cp templates/404.html site/404.html 2>/dev/null || echo '<!doctype html><title>Not found</title><p>Not found. <a href="/">Home</a></p>' > site/404.html

echo "==> Deploying stack $STACK in $REGION"
aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK" \
  --template-file infra/site.yaml \
  --no-fail-on-empty-changeset \
  --parameter-overrides DomainName="$DOMAIN" CertificateArn="$CERT_ARN" HostedZoneId="$ZONE_ID"

BUCKET=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
DIST=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text)
URL=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue" --output text)

echo "==> Syncing site/ to s3://$BUCKET"
aws s3 sync site/ "s3://$BUCKET/" --delete --region "$REGION" \
  --cache-control "public, max-age=300" --exclude "static/*"
aws s3 sync site/static/ "s3://$BUCKET/static/" --delete --region "$REGION" \
  --cache-control "public, max-age=86400"

echo "==> Invalidating CloudFront cache"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query "Invalidation.Id" --output text

echo
echo "Live at: $URL"
