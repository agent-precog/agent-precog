# agent-precog.org — living literature review

A living, PRISMA 2020 systematic review of pre-emptive safety for multi-agent AI, maintained for Project PreCog. The whole site is generated from three CSV files, so every number on it can be reproduced.

## Layout

```
data/papers.csv        every included paper (the single source of truth)
data/search_log.csv    every search run — the PRISMA-S record
data/decisions.csv     every screening decision, AI label and override
data/pillars.json      the five pillars and their search strings
data/changelog.csv     one row per release
version.json           current version, protocol version, next search date
build.py               generates site/ from the above
templates/             Jinja2 templates (home, pillar, papers, gap matrix, methods, changelog)
static/                CSS, logo, favicon
infra/site.yaml        CloudFormation: private S3 + CloudFront + OAC (+ optional domain)
infra/github-oidc-role.yaml  one-off: IAM role GitHub Actions assumes to deploy
deploy.sh              build + deploy in one command
.github/workflows/     deploys on every push to main
```

## Build locally

```bash
pip install jinja2
python3 build.py
python3 -m http.server -d site 8000   # then open http://localhost:8000
```

## Deploy to AWS (first time, from your laptop)

1. Install and configure the AWS CLI (`aws configure` or `aws sso login`). Pick a region; `eu-west-2` (London) is the default in `deploy.sh`.
2. Run `./deploy.sh`. It creates the stack, uploads the site and prints the CloudFront URL. That's the site live, with no domain yet.

## Add the custom domain (optional, any time later)

1. Register or transfer the domain in Route 53 (note the hosted zone ID).
2. In ACM **in us-east-1** (CloudFront requires that region), request a public certificate for the domain, validate via DNS (one click when the zone is in Route 53), copy its ARN.
3. Redeploy with the three values:
   ```bash
   DOMAIN=agent-precog.org CERT_ARN=arn:aws:acm:us-east-1:123456789012:certificate/... ZONE_ID=Z0123456789 ./deploy.sh
   ```
   The stack adds the alias and the A/AAAA records. Allow a few minutes for CloudFront to propagate.

## Deploy from GitHub automatically

1. One-off: deploy `infra/github-oidc-role.yaml` with your GitHub username (`aws cloudformation deploy --stack-name agent-precog-oidc --template-file infra/github-oidc-role.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides GitHubOrg=kd-gitgub`). Copy the `DeployRoleArn` output.
2. In the GitHub repo: Settings → Secrets → `AWS_DEPLOY_ROLE_ARN` = that ARN. Optionally Settings → Variables → `SITE_DOMAIN`, `SITE_CERT_ARN`, `SITE_ZONE_ID`.
3. Push to `main`. The workflow builds and deploys. No AWS keys are stored anywhere.

## Adding a paper

Append a row to `data/papers.csv` (columns are documented in the protocol's extraction template), commit, push. The pillar page, gap matrix and PRISMA counts update on the next build. `gap_cells` is a `;`-separated list drawn from: `multi-agent state`, `non-generative inference`, `latency/jitter aware`, `time-to-irreversibility`, `edge deployment`, `human handoff`, `cross-domain evaluation`.

## Cost

Domain £10–60/yr depending on TLD. S3 + CloudFront for a site this size: well under £1/month. Set a budget alarm in AWS Billing on day one.

## Licence

Content and data CC BY 4.0 (see LICENSE-CONTENT). Code MIT (see LICENSE).
