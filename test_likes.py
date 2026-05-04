import sys
import os

sys.path.append(os.path.abspath("source"))
from deno_service import DenoService
import paths

# Assuming paths.main_path is configured correctly
service = DenoService()
# Need to set paths.main_path or mock it if needed for the test
# For testing purpose, we'll assume the script is run from the root
paths.main_path = os.path.abspath("source")

# Mock cookies if needed, or pass an empty string
cookies_path = r"C:\Users\altrh\Downloads\youtube.txt"

# Test command
video_id = "rQH8vrOBrPs"
params = {"cookiesPath": cookies_path, "videoId": video_id}
result = service.send_command("get_video_likes", params)
print(f"Result: {result}")
