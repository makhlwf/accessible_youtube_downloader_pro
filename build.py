import os
import subprocess
import shutil

# It's better to run this from the repo root.
if not os.path.exists('source'):
    print("Error: This script should be run from the root of the repository.")
    exit(1)

# Clean up previous builds
if os.path.exists('dist'):
    shutil.rmtree('dist')
if os.path.exists('build'):
    shutil.rmtree('build')

# The entry point of the application
entry_point = os.path.join('source', 'accessible_youtube_downloader_pro.py')

# Name of the output executable
app_name = 'accessible_youtube_downloader_pro'

# Data files and directories to be included
# The format is 'source_path:destination_in_bundle'
# Using os.pathsep for the separator.
data_to_add = [
    # DLLs and EXEs
    'api-ms-win-core-path-l1-1-0.dll',
    'avcodec-60.dll',
    'avdevice-60.dll',
    'avfilter-9.dll',
    'avformat-60.dll',
    'avutil-58.dll',
    'ffmpeg.exe',
    'ffplay.exe',
    'ffprobe.exe',
    'libvlc.dll',
    'libvlccore.dll',
    'nvdaControllerClient32.dll',
    'nvdaControllerClient64.dll',
    'postproc-57.dll',
    'swresample-4.dll',
    'swscale-7.dll',
    # Directories
    'assets',
    'docs',
    'languages',
    'plugins',
]

# Construct the pyinstaller command
command = [
    'pyinstaller',
    '--noconfirm',
    '--windowed',
    '--onefile',
    '--name', app_name,
]

# Add data files to the command
for item in data_to_add:
    source_path = os.path.join('source', item)
    if os.path.isdir(source_path):
        # For directories, destination is the same as the directory name
        command.extend(['--add-data', f'{source_path}{os.pathsep}{item}'])
    elif os.path.isfile(source_path):
        # For files, destination is the root of the bundle
        command.extend(['--add-data', f'{source_path}{os.pathsep}.'])

# Add the entry point script at the end
command.append(entry_point)

print(f"Running command: {' '.join(command)}")

# Run the command
try:
    subprocess.run(command, check=True)
    print("Build completed successfully!")
    print(f"The executable is in the 'dist' directory.")
except subprocess.CalledProcessError as e:
    print(f"Build failed with error: {e}")
    exit(1)
except FileNotFoundError:
    print("Error: pyinstaller is not installed or not in the system's PATH.")
    print("Please install it using: pip install pyinstaller")
    exit(1)
