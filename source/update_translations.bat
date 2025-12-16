@echo off

set PROJECT_NAME=AccessibleYoutubeDownloaderPro
set PROJECT_VERSION=8.0
set AUTHOR_NAME=Makhlwf
set AUTHOR_EMAIL=Altrhwnyashrf1@gmail.com

echo === Extracting messages ===
pybabel extract ^
    -F babel.cfg ^
    -o languages/messages.pot ^
    --project="%PROJECT_NAME%" ^
    --version="%PROJECT_VERSION%" ^
    --copyright-holder="%AUTHOR_NAME%" ^
    --msgid-bugs-address="%AUTHOR_EMAIL%" ^
    --last-translator="%AUTHOR_NAME% <%AUTHOR_EMAIL%>" ^
    .

echo === Updating translations ===
pybabel update -d languages -i languages/messages.pot --update-header-comment

echo === Compiling ===
pybabel compile -d languages

echo === Done ===
pause
