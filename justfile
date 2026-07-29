# use PowerShell instead of sh:
set shell := ["powershell.exe", "-c"]

#using uv run to run the app
run:
  uv run src\accessible_youtube_downloader_pro.py

# using BuildNPackage.bat to run the build .py and iscc inno.iss fcommand, i should let just do it but this is something for later, at least it does the job now.
package:
  ./BuildNPackage.bat