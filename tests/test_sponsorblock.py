import os
from unittest.mock import MagicMock, patch

import sponsorblock_handler
from paths import settings_path
from settings_handler import config_get, config_initialization, config_set, defaults
from sponsorblock_handler import (
    CATEGORIES,
    DEFAULT_API_URL,
    category_label,
    category_labels,
    extract_video_id,
    filter_skippable_segments,
    find_skip_segment,
    find_skip_target,
    format_categories,
    get_api_base_url,
    get_enabled_categories,
    get_min_segment_duration,
    get_sponsorblock_segments,
    is_skippable_segment,
    parse_categories,
    should_announce_skips,
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


def test_sponsorblock_option_defaults():
    assert defaults["sponsorblock_notify"] is True
    assert defaults["sponsorblock_min_duration"] == 0.0
    assert defaults["sponsorblock_api_url"] == DEFAULT_API_URL
    assert parse_categories(defaults["sponsorblock_categories"]) == list(CATEGORIES)


def test_parse_categories():
    assert parse_categories("sponsor,intro") == ["sponsor", "intro"]
    # Unknown names are dropped and the canonical order is restored.
    assert parse_categories("INTRO , sponsor , nonsense") == ["sponsor", "intro"]
    # An explicit empty value means "skip nothing".
    assert parse_categories("") == []
    # A missing or malformed value falls back to the defaults.
    assert parse_categories(None) == list(CATEGORIES)
    assert parse_categories(False) == list(CATEGORIES)


def test_format_categories():
    assert format_categories(["intro", "sponsor", "nonsense"]) == "sponsor,intro"
    assert format_categories([]) == ""
    assert format_categories(None) == ""
    assert parse_categories(format_categories(CATEGORIES)) == list(CATEGORIES)


def test_category_labels_cover_every_category():
    labels = category_labels()
    assert set(labels) == set(CATEGORIES)
    assert all(labels.values())
    assert category_label("sponsor") == labels["sponsor"]
    assert category_label("unknown_category") == "unknown_category"
    assert category_label(None) == ""


def test_sponsorblock_settings_helpers(monkeypatch):
    values = {
        "sponsorblock_categories": "sponsor",
        "sponsorblock_min_duration": "2.5",
        "sponsorblock_api_url": "  https://sb.example.com/  ",
        "sponsorblock_notify": False,
    }
    monkeypatch.setattr(sponsorblock_handler, "config_get", values.get)

    assert get_enabled_categories() == ["sponsor"]
    assert get_min_segment_duration() == 2.5
    assert get_api_base_url() == "https://sb.example.com"
    assert should_announce_skips() is False

    values["sponsorblock_min_duration"] = "not a number"
    assert get_min_segment_duration() == 0.0
    values["sponsorblock_min_duration"] = -5.0
    assert get_min_segment_duration() == 0.0
    values["sponsorblock_api_url"] = ""
    assert get_api_base_url() == DEFAULT_API_URL
    values["sponsorblock_notify"] = None
    assert should_announce_skips() is True


def test_is_skippable_segment():
    assert is_skippable_segment(FakeSegment(0.0, 10.0)) is True
    # Only "skip" segments may move playback.
    assert is_skippable_segment(FakeSegment(0.0, 10.0, action_type="mute")) is False
    assert is_skippable_segment(FakeSegment(0.0, 900.0, action_type="full")) is False
    assert (
        is_skippable_segment(
            FakeSegment(5.0, 5.0, category="poi_highlight", action_type="poi")
        )
        is False
    )
    # Minimum duration.
    assert is_skippable_segment(FakeSegment(0.0, 3.0), min_duration=5.0) is False
    assert is_skippable_segment(FakeSegment(0.0, 6.0), min_duration=5.0) is True
    # Disabled categories.
    intro = FakeSegment(0.0, 10.0, category="intro")
    assert is_skippable_segment(intro, ["sponsor"]) is False
    assert is_skippable_segment(intro, ["sponsor", "intro"]) is True


def test_get_sponsorblock_segments_honours_settings(monkeypatch):
    mock_client = MagicMock()
    mock_client.get_skip_segments.return_value = [
        FakeSegment(0.0, 20.0),
        FakeSegment(30.0, 40.0, category="intro"),  # category turned off
        FakeSegment(50.0, 60.0, action_type="mute"),  # not a skip segment
        FakeSegment(70.0, 71.0),  # shorter than the minimum
    ]
    values = {
        "sponsorblock_categories": "sponsor",
        "sponsorblock_min_duration": 2.0,
    }
    monkeypatch.setattr(sponsorblock_handler, "config_get", values.get)
    monkeypatch.setattr(
        sponsorblock_handler, "get_sponsorblock_client", lambda: mock_client
    )

    segments = get_sponsorblock_segments("kJQP7kiw5Fk")
    assert [(s.start, s.end) for s in segments] == [(0.0, 20.0)]
    assert mock_client.get_skip_segments.call_args.kwargs["categories"] == ["sponsor"]


def test_get_sponsorblock_segments_without_any_category(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(
        sponsorblock_handler,
        "config_get",
        lambda key: "" if key == "sponsorblock_categories" else None,
    )
    monkeypatch.setattr(
        sponsorblock_handler, "get_sponsorblock_client", lambda: mock_client
    )

    assert get_sponsorblock_segments("kJQP7kiw5Fk") == []
    mock_client.get_skip_segments.assert_not_called()


def test_client_is_rebuilt_when_the_server_changes(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            created.append(kwargs.get("base_url"))

    monkeypatch.setattr(sponsorblock_handler, "_client", None)
    monkeypatch.setattr(sponsorblock_handler, "_client_base_url", None)
    monkeypatch.setattr(sponsorblock_handler.sponsorblock, "Client", FakeClient)
    url = {"value": "https://one.example.com"}
    monkeypatch.setattr(
        sponsorblock_handler,
        "config_get",
        lambda key: url["value"] if key == "sponsorblock_api_url" else None,
    )

    first = sponsorblock_handler.get_sponsorblock_client()
    assert sponsorblock_handler.get_sponsorblock_client() is first
    assert created == ["https://one.example.com"]

    url["value"] = "https://two.example.com"
    assert sponsorblock_handler.get_sponsorblock_client() is not first
    assert created == ["https://one.example.com", "https://two.example.com"]


def test_find_skip_segment_reports_the_category():
    segments = [FakeSegment(10.0, 20.0, category="intro")]
    assert find_skip_segment(12.0, segments) == (20.0, "intro")
    assert find_skip_segment(0.0, segments) is None
    assert find_skip_target(12.0, segments) == 20.0


def test_filter_skippable_segments_reapplies_current_settings(monkeypatch):
    # A list fetched while every category was enabled.
    segments = [
        FakeSegment(100.0, 120.0, category="intro"),
        FakeSegment(0.0, 20.0),
        FakeSegment(50.0, 51.0),
        FakeSegment(200.0, 260.0, action_type="mute"),
    ]
    values = {
        "sponsorblock_categories": "sponsor",
        "sponsorblock_min_duration": 5.0,
    }
    monkeypatch.setattr(sponsorblock_handler, "config_get", values.get)

    # Sorted by start time, with the disabled category, the short segment and the
    # non-skip segment dropped.
    assert [(s.start, s.end) for s in filter_skippable_segments(segments)] == [
        (0.0, 20.0)
    ]

    values["sponsorblock_categories"] = "sponsor,intro"
    values["sponsorblock_min_duration"] = 0.0
    assert [(s.start, s.end) for s in filter_skippable_segments(segments)] == [
        (0.0, 20.0),
        (50.0, 51.0),
        (100.0, 120.0),
    ]

    values["sponsorblock_categories"] = ""
    assert filter_skippable_segments(segments) == []
    assert filter_skippable_segments(None) == []
    assert filter_skippable_segments([]) == []


def test_mediagui_refilters_segments_attached_to_the_stream(monkeypatch):
    from media_player import media_gui
    from media_player.mpv_backend import State

    # The stream carries a list fetched before "intro" was turned off.
    stream = Stream(
        "Test",
        "http://stream.url",
        sponsorblock_segments=[
            FakeSegment(10.0, 25.0, category="intro"),
            FakeSegment(40.0, 60.0),
        ],
    )
    monkeypatch.setattr(
        sponsorblock_handler,
        "config_get",
        lambda key: "sponsor" if key == "sponsorblock_categories" else None,
    )

    with (
        patch.object(
            media_gui,
            "config_get",
            side_effect=lambda k: k == "sponsorblock",
        ),
        patch.object(media_gui, "Player") as MockPlayer,
        patch.object(media_gui.MediaGui, "fetch_qualities"),
        patch.object(media_gui.MediaGui, "fetch_chapters"),
        patch.object(media_gui.MediaGui, "fetch_subtitles"),
        patch.object(media_gui.MediaGui, "extract_description"),
        patch.object(media_gui.MediaGui, "fetch_like_count"),
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

        # Only the sponsor segment survives, so the intro is no longer skipped.
        assert [(s.start, s.end) for s in gui.sponsorblock_segments] == [(40.0, 60.0)]
        mock_player_instance.media.get_time.return_value = 12000
        gui.on_sponsorblock_timer(None)
        mock_player_instance.media.set_time.assert_not_called()

        gui.closeAction()


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


def test_settings_dialog_sponsorblock_block():
    from gui import settings_dialog

    with patch.object(settings_dialog, "config_get", return_value=False):
        dlg = settings_dialog.SettingsDialog(None)

    assert list(dlg.sponsorBlockCategories) == list(CATEGORIES)
    assert dlg.sponsorBlockNotify.Name == "sponsorblock_notify"
    assert dlg.sponsorBlockApiUrl.Value == DEFAULT_API_URL
    # Nothing stored yet, so every category starts enabled.
    assert all(box.GetValue() for box in dlg.sponsorBlockCategories.values())
    # The details stay greyed out until SponsorBlock itself is turned on.
    assert dlg.sponsorBlockNotify.IsEnabled() is False
    assert not any(box.IsEnabled() for box in dlg.sponsorBlockCategories.values())

    dlg.sponsorBlock.SetValue(True)
    dlg._update_sponsorblock_controls()
    assert dlg.sponsorBlockNotify.IsEnabled() is True
    assert all(box.IsEnabled() for box in dlg.sponsorBlockCategories.values())


def test_settings_dialog_saves_sponsorblock_settings():
    from gui import settings_dialog

    with patch.object(settings_dialog, "config_get", return_value=False):
        dlg = settings_dialog.SettingsDialog(None)

    for category, box in dlg.sponsorBlockCategories.items():
        box.SetValue(category in ("intro", "sponsor"))
    dlg.sponsorBlockApiUrl.Value = "sb.example.com"

    saved = {}
    with patch.object(
        settings_dialog, "config_set", lambda key, value: saved.update({key: value})
    ):
        dlg._save_sponsorblock_settings()

    assert saved["sponsorblock_categories"] == "sponsor,intro"
    # A server without a scheme is completed instead of rejected.
    assert saved["sponsorblock_api_url"] == "https://sb.example.com"
    assert saved["sponsorblock_min_duration"] == 0.0


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
        patch.object(media_gui.MediaGui, "fetch_qualities"),
        patch.object(media_gui.MediaGui, "fetch_chapters"),
        patch.object(media_gui.MediaGui, "fetch_subtitles"),
        patch.object(media_gui.MediaGui, "extract_description"),
        patch.object(media_gui.MediaGui, "fetch_like_count"),
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
