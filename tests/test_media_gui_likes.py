from media_player import media_gui


def test_fetch_like_count_updates_like_count_and_rating(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    gui.like_count = None
    gui.rating = None

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(media_gui, "Thread", ImmediateThread)
    monkeypatch.setattr(
        media_gui.utils,
        "get_video_like_info",
        lambda url: {"likes": 42, "rating": "like"},
    )

    gui.fetch_like_count()

    assert gui.like_count == 42
    assert gui.rating == "like"
