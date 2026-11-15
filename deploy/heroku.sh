#!/bin/sh
# Deploy the public demo to Heroku from a build context assembled outside the repo.
# The context (code, git-ignored data/raw and two CoStar kit files) is pushed only to Heroku's own git,
# never to GitHub. No .env and no API keys are included.
# Usage: sh deploy/heroku.sh <heroku-app-name>   (needs `heroku login` first)
set -eu
app=$1
repo=$(cd "$(dirname "$0")/.." && pwd)
out=${TMPDIR:-/tmp}/secondstay-heroku

SKIP_DEPLOY=1 sh "$repo/deploy/build.sh" "$out"
cd "$out"
mv app/* app/.[!.]* . 2>/dev/null || true
rmdir app
rm -f Dockerfile fly.toml
printf 'web: python -m secondstay.web\n' > Procfile
printf 'pillow\ndeepagents==0.7.38\nlangchain-openai>=1.8,<2\n' > requirements.txt  # the AI check runs on the judges' link
printf '3.12\n' > .python-version

# Offline for maps and scans; AI runs open only to requests carrying JUDGE_KEY (set it with heroku config:set).
heroku config:set -a "$app" COSTAR_KIT_DIR=/app/kit SECONDSTAY_OFFLINE=1 HOST=0.0.0.0 SECONDSTAY_ALLOW_AI=1 \
  SECONDSTAY_AGENT_PROVIDER=openai SECONDSTAY_AGENT_MODEL=gpt-5.4-mini >/dev/null
git init -q
git add -A
git -c user.name=deploy -c user.email=deploy@localhost commit -qm "Deploy $(date -u +%Y-%m-%dT%H:%MZ)"
git push -f "https://git.heroku.com/$app.git" HEAD:main
