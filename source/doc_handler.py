from settings_handler import config_get
import os
import application
import paths

def documentation_get():
    docs_path = os.path.join(paths.get_bundled_data_path(), "docs")
    available_languages = os.listdir(docs_path)
    lang = config_get("lang")
    if lang not in available_languages:
        lang = "ar"
    path = os.path.join(docs_path, lang, "guide.txt")
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        namespace = {
            "name": application.name,
            "version": application.version,
            "author": application.author,
        }
        return file.read().format(**namespace)
