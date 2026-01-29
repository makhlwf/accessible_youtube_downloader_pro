# HexPlayer

A windows app for brousing, watching, and downloading of Youtube content

# features
1. **Simple UI**: the app comes with a simple user interface that helps you get the most out of the app
2. **OS compatibility**: the app is highly proforment on windows, making operations faster

# downloading
you can get the latest upto dated version for the app from the releases page

# running from source
1. clone this repo locally
```
git clone https://github.com/makhlwf/accessible_youtube_downloader_pro.git
```
2. ensure you have python 3.11 installed
3. install uv if you didn't
```
pip install --upgrade uv
```
4. cd to the cloned repo
5. make a venv, change the value after -p to the python version you want the app to run with, i use 3.14
```
uv venv -p 3.14
```
6. activate the venv
```
.venv\Scripts\activate
```
7. install all the needed Dependencies to run
```
uv pip install -r requirements.txt
```
9. cd to source folder
```
cd source
```
10. run the app
```
uv run accessible_youtube_downloader_pro.py
```

# building the app
if you need to make an exe do this after conferming that the app works
1. ensure that you are in the root folder of the repo
2. ensure you have activated the venv
3. install pyinstaller
```
uv pip install --upgrade pyinstaller
```
4. run the build Script
```
uv run build.py
```
5. after compleating you will find the files in the dist folder


# ⚠️ Disclaimer

This project is a fork of the original Acessible Youtube Downloader Pro repository created by Sulaiman Al Qusaimi. I am not the original developer of this application.