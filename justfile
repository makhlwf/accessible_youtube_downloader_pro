# use PowerShell instead of sh:
set shell := ["powershell.exe", "-c"]

#using uv run to run the app
run:
  uv run src\accessible_youtube_downloader_pro.py

# run all agent & developer preflight quality gates
preflight:
  uv run python scripts/agent_preflight.py

# validate that all skills in .agents/skills/ match the latest agentskills.io format
verify-skills:
  uv run python scripts/verify_skills.py

# using BuildNPackage.bat to run the build .py and iscc inno.iss fcommand, i should let just do it but this is something for later, at least it does the job now.
package:
  ./BuildNPackage.bat