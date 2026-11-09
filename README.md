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
data/raw/              database exports and API downloads, one file per run and database
data/screening/        per-run normalised records, AI labels, review workbooks, full-text queues, prompts/
search.py              queries arXiv, OpenAlex and Semantic Scholar with a pillar's string (count or download)
ingest.py              normalises exports/downloads and deduplicates against earlier runs and included papers
label.py               AI title/abstract labelling with a versioned prompt (Amazon Bedrock)
review.py              builds the maintainer's review workbook; applies the returned workbook to decisions.csv
build.py               generates site/ from the above
templates/             Jinja2 templates (home, pillar, papers, gap matrix, methods, changelog)
static/                CSS, logo, favicon
infra/site.yaml        CloudFormation: private S3 + CloudFront + OAC (+ optional domain)
infra/github-oidc-role.yaml  one-off: IAM role GitHub Actions assumes to deploy
deploy.sh              build + deploy in one command
.github/workflows/     deploy.yml deploys on every push to main; search.yml runs the living search monthly
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

1. One-off: deploy `infra/github-oidc-role.yaml` with your GitHub username (`aws cloudformation deploy --stack-name agent-precog-oidc --template-file infra/github-oidc-role.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides GitHubOrg=agent-precog`). Copy the `DeployRoleArn` output.
2. In the GitHub repo: Settings → Secrets → `AWS_DEPLOY_ROLE_ARN` = that ARN. Optionally Settings → Variables → `SITE_DOMAIN`, `SITE_CERT_ARN`, `SITE_ZONE_ID`.
3. Push to `main`. The workflow builds and deploys. No AWS keys are stored anywhere.

## Living search (automated runs)

`.github/workflows/search.yml` runs on the 15th of each month and on demand (Actions → Living search → Run workflow,
choosing pillar, databases and `count` or `screen` mode). In `screen` mode it downloads the records, deduplicates them
against every earlier run and every included paper, labels them with the current screening prompt through Bedrock, builds
the maintainer's review workbook and opens a pull request. The maintainer fills the workbook, runs
`python3 review.py apply --run <run> --sheet <returned.xlsx>`, commits, and merges; only then do the records count in the
PRISMA flow. Setup, once: redeploy `infra/github-oidc-role.yaml` and put its `SearchRoleArn` output in the secret
`AWS_SEARCH_ROLE_ARN`; optionally set the variable `OPENALEX_MAILTO` (an email for OpenAlex's polite pool) and the secret
`S2_API_KEY` (free Semantic Scholar key); and allow GitHub Actions to create pull requests (Settings → Actions → General).
Publisher databases (IEEE Xplore, ACM) are searched by hand and their exports dropped into `data/raw/` for `ingest.py`.

## Adding a paper

Append a row to `data/papers.csv` (columns are documented in the protocol's extraction template), commit, push. The pillar page, gap matrix and PRISMA counts update on the next build. `gap_cells` is a `;`-separated list drawn from: `multi-agent state`, `non-generative inference`, `latency/jitter aware`, `time-to-irreversibility`, `edge deployment`, `human handoff`, `cross-domain evaluation`.

## Licence

Content and data CC BY 4.0 (see LICENSE-CONTENT). Code MIT (see LICENSE).
