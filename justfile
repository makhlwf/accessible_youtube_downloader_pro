set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

run:
  uv run python src/accessible_youtube_downloader_pro.py

preflight:
  uv run python scripts/agent_preflight.py

verify-skills:
  uv run python scripts/verify_skills.py

lint:
  uv run --only-dev ruff check .
  uv run --only-dev ruff format --check .

test:
  uv run pytest tests/

translations:
  uv run --only-dev python scripts/check_translations.py

build:
  uv run --locked --no-dev --group build python scripts/build.py

[windows]
package: build
  iscc packaging/windows/inno.iss

[linux]
package: build

[linux]
linux-deps:
  sudo bash packaging/linux/install-deps.sh
