import asyncio
import builtins
import sys
import os

# Add current directory to sys.path
sys.path.append(os.getcwd())

# Mock _() for translation
builtins._ = lambda x: x

from py_yt import Playlist

async def test_playlist_data():
    # A public playlist
    url = "https://www.youtube.com/playlist?list=PLzMcBGfZo4-kCLWHEm9V9RLherbRVoqx7" 
    print(f"Fetching playlist: {url}")
    try:
        playlist_data = await Playlist.getVideos(url)
        videos = playlist_data.get("videos", [])
        print(f"Found {len(videos)} videos.")
        if videos:
            first = videos[0]
            print("First video data keys:", first.keys())
            print("First video details:")
            for k, v in first.items():
                if k != 'thumbnails': # Avoid clutter
                    print(f"  {k}: {v}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_playlist_data())
