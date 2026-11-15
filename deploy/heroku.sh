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
printf 'pillow\n' > requirements.txt
printf '3.12\n' > .python-version

heroku config:set -a "$app" COSTAR_KIT_DIR=/app/kit SECONDSTAY_OFFLINE=1 HOST=0.0.0.0 >/dev/null
git init -q
git add -A
git -c user.name=deploy -c user.email=deploy@localhost commit -qm "Deploy $(date -u +%Y-%m-%dT%H:%MZ)"
git push -f "https://git.heroku.com/$app.git" HEAD:main
