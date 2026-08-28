import os
from unittest.mock import MagicMock, patch

from paths import settings_path
from settings_handler import config_get, config_initialization, config_set, defaults
from sponsorblock_handler import (
    extract_video_id,
    find_skip_target,
    get_sponsorblock_segments,
)
from utils import Stream, _attach_sponsorblock_segments


class FakeSegment:
    def __init__(self, start, end, category="sponsor", action_type="skip"):
        self.start = float(start)
        self.end = float(end)
        self.category = category
        self.action_type = action_type


def test_sponsorblock_setting_default():
    assert "sponsorblock" in defaults
    assert defaults["sponsorblock"] is False


def test_sponsorblock_setting_persistence():
    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))
    config_initialization()

    assert config_get("sponsorblock") is False
    config_set("sponsorblock", True)
    assert config_get("sponsorblock") is True
    config_set("sponsorblock", False)
    assert config_get("sponsorblock") is False

    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))


def test_settings_dialog_has_sponsorblock():
    from gui import settings_dialog

    with patch.object(settings_dialog, "config_get", return_value=False):
        dlg = settings_dialog.SettingsDialog(None)
        assert hasattr(dlg, "sponsorBlock")
        assert dlg.sponsorBlock.Name == "sponsorblock"
        assert dlg.sponsorBlock.GetValue() is False


def test_extract_video_id():
    assert (
        extract_video_id("https://www.youtube.com/watch?v=kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    )
    assert extract_video_id("https://youtu.be/kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    assert (
        extract_video_id("https://www.youtube.com/shorts/kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    )
    assert (
        extract_video_id("https://www.youtube.com/embed/kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    )
    assert extract_video_id("kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    assert extract_video_id("") is None
    assert extract_video_id(None) is None
    assert extract_video_id("https://example.com/not-youtube") is None
    assert extract_video_id("not_a_valid_id") is None


def test_get_sponsorblock_segments_success():
    mock_client = MagicMock()
    mock_client.get_skip_segments.return_value = [
        FakeSegment(100.0, 120.0),
        FakeSegment(0.0, 15.0),
        FakeSegment(50.0, 50.0),  # Zero duration, should be filtered
        FakeSegment(70.0, 60.0),  # Negative duration, should be filtered
    ]

    with patch(
        "sponsorblock_handler.get_sponsorblock_client",
        return_value=mock_client,
    ):
        segments = get_sponsorblock_segments(
            "https://www.youtube.com/watch?v=kJQP7kiw5Fk"
        )
        assert len(segments) == 2
        # Should be sorted by start time
        assert segments[0].start == 0.0
        assert segments[0].end == 15.0
        assert segments[1].start == 100.0
        assert segments[1].end == 120.0


def test_get_sponsorblock_segments_empty_or_error():
    mock_client = MagicMock()
    mock_client.get_skip_segments.return_value = []

    with patch(
        "sponsorblock_handler.get_sponsorblock_client",
        return_value=mock_client,
    ):
        assert get_sponsorblock_segments("kJQP7kiw5Fk") == []

    mock_client.get_skip_segments.side_effect = Exception("API error")
    with patch(
        "sponsorblock_handler.get_sponsorblock_client",
        return_value=mock_client,
    ):
        assert get_sponsorblock_segments("kJQP7kiw5Fk") == []

    assert get_sponsorblock_segments("") == []


def test_find_skip_target_single_segment():
    segments = [FakeSegment(10.0, 20.0)]

    assert find_skip_target(0.0, segments) is None
    assert find_skip_target(9.9, segments) is None
    assert find_skip_target(10.0, segments) == 20.0
    assert find_skip_target(15.0, segments) == 20.0
    assert find_skip_target(19.9, segments) == 20.0
    assert find_skip_target(20.0, segments) is None
    assert find_skip_target(25.0, segments) is None


def test_find_skip_target_overlapping_and_contiguous():
    # Overlapping: [10, 20] and [18, 30] -> merged [10, 30]
    segments = [FakeSegment(10.0, 20.0), FakeSegment(18.0, 30.0)]
    assert find_skip_target(12.0, segments) == 30.0
    assert find_skip_target(22.0, segments) == 30.0

    # Contiguous: [0, 10] and [10, 25] -> merged [0, 25]
    segments_contig = [FakeSegment(0.0, 10.0), FakeSegment(10.0, 25.0)]
    assert find_skip_target(0.0, segments_contig) == 25.0
    assert find_skip_target(5.0, segments_contig) == 25.0


def test_find_skip_target_edge_cases():
    assert find_skip_target(None, [FakeSegment(0, 10)]) is None
    assert find_skip_target(-1.0, [FakeSegment(0, 10)]) is None
    assert find_skip_target(5.0, []) is None
    assert find_skip_target(5.0, None) is None


def test_stream_sponsorblock_segments_attachment():
    stream = Stream("Test Title", "http://stream.url")
    assert stream.sponsorblock_segments is None

    # When sponsorblock is disabled
    with patch("utils.config_get", return_value=False):
        attached = _attach_sponsorblock_segments(
            stream, "https://youtube.com/watch?v=12345678901"
        )
        assert attached.sponsorblock_segments is None

    # When sponsorblock is enabled
    fake_segs = [FakeSegment(0.0, 10.0)]
    with (
        patch("utils.config_get", return_value=True),
        patch(
            "sponsorblock_handler.get_sponsorblock_segments",
            return_value=fake_segs,
        ),
    ):
        attached = _attach_sponsorblock_segments(
            stream, "https://youtube.com/watch?v=12345678901"
        )
        assert attached.sponsorblock_segments == fake_segs


def test_mediagui_sponsorblock_skipping():
    from media_player import media_gui
    from media_player.mpv_backend import State

    stream = Stream(
        "Test",
        "http://stream.url",
        sponsorblock_segments=[FakeSegment(10.0, 25.0)],
    )

    with (
        patch.object(
            media_gui,
            "config_get",
            side_effect=lambda k: k == "sponsorblock",
        ),
        patch.object(media_gui, "Player") as MockPlayer,
    ):
        mock_player_instance = MagicMock()
        mock_player_instance.media.get_state.return_value = State.Playing
        mock_player_instance.media.get_time.return_value = 0
        MockPlayer.return_value = mock_player_instance

        gui = media_gui.MediaGui(
            None,
            "Test Title",
            stream,
            "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        )

        assert len(gui.sponsorblock_segments) == 1

        # Test skip during timer tick
        mock_player_instance.media.get_time.return_value = 12000  # 12s, inside [10, 25]
        with patch.object(media_gui, "speak") as mock_speak:
            gui.on_sponsorblock_timer(None)
            mock_player_instance.media.set_time.assert_called_with(25000)
            mock_speak.assert_called_once()

        gui.closeAction()
