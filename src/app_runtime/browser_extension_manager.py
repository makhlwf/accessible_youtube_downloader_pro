import os
import shutil

import paths

BROWSER_EXTENSION_DIR = "browser_extension"


def get_bundled_extension_path():
    return os.path.join(paths.get_bundled_data_path(), BROWSER_EXTENSION_DIR)


def get_user_extension_path():
    return os.path.join(paths.settings_path, BROWSER_EXTENSION_DIR)


def sync_browser_extension_files():
    source_path = get_bundled_extension_path()
    target_path = get_user_extension_path()
    if not os.path.isdir(source_path):
        return ""

    os.makedirs(paths.settings_path, exist_ok=True)
    temp_path = f"{target_path}.new"
    if os.path.isdir(temp_path):
        shutil.rmtree(temp_path)

    shutil.copytree(source_path, temp_path)
    try:
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        os.replace(temp_path, target_path)
    except OSError:
        shutil.copytree(source_path, target_path, dirs_exist_ok=True)
        if os.path.isdir(temp_path):
            shutil.rmtree(temp_path)
    return target_path
