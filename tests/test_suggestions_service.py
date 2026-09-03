import sys
from unittest.mock import AsyncMock, patch

# Ensure real py_yt package is used if a non-package mock was registered by conftest
if "py_yt" in sys.modules and not hasattr(sys.modules["py_yt"], "__path__"):
    del sys.modules["py_yt"]

from media_player.suggestions_service import (
    SuggestionsService,
    extract_video_id,
    parse_compact_video,
    parse_lockup_view_model,
)


def test_parse_lockup_view_model():
    mock_item = {
        "lockupViewModel": {
            "contentId": "test_vid_123",
            "metadata": {
                "lockupMetadataViewModel": {
                    "title": {"content": "Sample Test Video"},
                    "metadata": {
                        "contentMetadataViewModel": {
                            "metadataRows": [
                                {
                                    "metadataParts": [
                                        {"text": {"content": "Test Artist Channel"}}
                                    ]
                                },
                                {
                                    "metadataParts": [
                                        {"text": {"content": "1.2M views"}}
                                    ]
                                },
                            ]
                        }
                    },
                }
            },
            "contentImage": {
                "thumbnailViewModel": {
                    "overlays": [
                        {
                            "thumbnailBottomOverlayViewModel": {
                                "badges": [
                                    {"thumbnailBadgeViewModel": {"text": "03:45"}}
                                ]
                            }
                        }
                    ]
                }
            },
        }
    }

    parsed = parse_lockup_view_model(mock_item)
    assert parsed is not None
    assert parsed["id"] == "test_vid_123"
    assert parsed["title"] == "Sample Test Video"
    assert parsed["channel"]["name"] == "Test Artist Channel"
    assert parsed["duration"] == "03:45"
    assert parsed["url"] == "https://www.youtube.com/watch?v=test_vid_123"
    assert parsed["views"] == "1.2M views"


def test_parse_lockup_view_model_empty_or_invalid():
    assert parse_lockup_view_model({}) is None
    assert parse_lockup_view_model({"lockupViewModel": {}}) is None
    assert parse_lockup_view_model({"lockupViewModel": {"contentId": ""}}) is None


def test_recommendations_aliases():
    from py_yt import Recommendations

    # Import suggestions_service ensures aliases are configured
    import media_player.suggestions_service  # noqa: F401

    assert hasattr(Recommendations, "getRelated")
    assert hasattr(Recommendations, "getHome")
    assert Recommendations.getRelated == Recommendations.get_related
    assert Recommendations.getHome == Recommendations.get_home


def test_extract_video_id():
    assert extract_video_id("https://youtu.be/abc12345?t=10") == "abc12345"
    assert (
        extract_video_id("https://www.youtube.com/watch?v=xyz98765&feature=shared")
        == "xyz98765"
    )
    assert extract_video_id("https://www.youtube.com/shorts/short_id_1") == "short_id_1"
    assert extract_video_id("https://www.youtube.com/embed/embed_id_1") == "embed_id_1"
    assert extract_video_id("https://example.com/not_youtube") is None
    assert extract_video_id("") is None
    assert extract_video_id(None) is None


def test_parse_compact_video():
    item = {
        "compactVideoRenderer": {
            "videoId": "compact_123",
            "title": {"simpleText": "Compact Video Title"},
            "shortBylineText": {"runs": [{"text": "Compact Channel"}]},
            "lengthText": {"simpleText": "10:20"},
        }
    }
    parsed = parse_compact_video(item)
    assert parsed is not None
    assert parsed["id"] == "compact_123"
    assert parsed["title"] == "Compact Video Title"
    assert parsed["channel"]["name"] == "Compact Channel"
    assert parsed["duration"] == "10:20"

    item_headline = {
        "videoWithContextRenderer": {
            "videoId": "context_456",
            "headline": {"runs": [{"text": "Context Video Title"}]},
            "shortBylineText": {"runs": [{"text": "Context Channel"}]},
            "lengthText": {"runs": [{"text": "05:00"}]},
        }
    }
    parsed_hl = parse_compact_video(item_headline)
    assert parsed_hl is not None
    assert parsed_hl["id"] == "context_456"
    assert parsed_hl["title"] == "Context Video Title"
    assert parsed_hl["duration"] == "05:00"

    assert parse_compact_video({}) is None
    assert parse_compact_video({"compactVideoRenderer": {}}) is None


@patch("media_player.suggestions_service.RelatedVideosCore")
def test_fetch_related_success(mock_core_cls):
    instance = mock_core_cls.return_value
    instance._make_request = AsyncMock()

    raw_response = {
        "contents": {
            "twoColumnWatchNextResults": {
                "secondaryResults": {
                    "secondaryResults": {
                        "results": [
                            {
                                "lockupViewModel": {
                                    "contentId": "rel_vid_1",
                                    "metadata": {
                                        "lockupMetadataViewModel": {
                                            "title": {"content": "Related Video 1"},
                                            "metadata": {
                                                "contentMetadataViewModel": {
                                                    "metadataRows": [
                                                        {
                                                            "metadataParts": [
                                                                {
                                                                    "text": {
                                                                        "content": "Channel 1"
                                                                    }
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }
                                            },
                                        }
                                    },
                                    "contentImage": {
                                        "thumbnailViewModel": {
                                            "overlays": [
                                                {
                                                    "thumbnailBottomOverlayViewModel": {
                                                        "badges": [
                                                            {
                                                                "thumbnailBadgeViewModel": {
                                                                    "text": "04:20"
                                                                }
                                                            }
                                                        ]
                                                    }
                                                }
                                            ]
                                        }
                                    },
                                }
                            },
                            {
                                "continuationItemRenderer": {
                                    "continuationEndpoint": {
                                        "continuationCommand": {
                                            "token": "continuation_token_abc"
                                        }
                                    }
                                }
                            },
                        ]
                    }
                }
            }
        }
    }

    instance.responseSource = raw_response

    def mock_get_value(source, keys):
        curr = source
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return None
        return curr

    instance._get_value.side_effect = mock_get_value

    res = SuggestionsService.fetch_related(
        "https://www.youtube.com/watch?v=rel_vid_1", limit=10
    )
    assert len(res["videos"]) == 1
    assert res["videos"][0]["id"] == "rel_vid_1"
    assert res["videos"][0]["title"] == "Related Video 1"
    assert res["continuation"] == "continuation_token_abc"


def test_fetch_related_invalid_url():
    res = SuggestionsService.fetch_related("invalid-url")
    assert res == {"videos": [], "continuation": None}


def test_parse_lockup_view_model_with_none_values():
    mock_item = {
        "lockupViewModel": {
            "contentId": "test_none",
            "metadata": None,
            "contentImage": None,
        }
    }
    parsed = parse_lockup_view_model(mock_item)
    assert parsed is not None
    assert parsed["id"] == "test_none"
    assert parsed["title"] == ""
    assert parsed["channel"]["name"] == ""
    assert parsed["duration"] == ""
    assert parsed["views"] is None


def test_parse_compact_video_with_none_values():
    mock_item = {
        "compactVideoRenderer": {
            "videoId": "compact_none",
            "title": None,
            "shortBylineText": None,
            "lengthText": None,
        }
    }
    parsed = parse_compact_video(mock_item)
    assert parsed is not None
    assert parsed["id"] == "compact_none"
    assert parsed["title"] == ""
    assert parsed["channel"]["name"] == ""
    assert parsed["duration"] == ""


@patch("media_player.suggestions_service.RelatedVideosCore")
def test_fetch_related_preserves_continuation_at_limit(mock_core_cls):
    instance = mock_core_cls.return_value
    instance._make_request = AsyncMock()

    # Create 20 videos followed by 1 continuation item
    items = []
    for i in range(20):
        items.append(
            {
                "lockupViewModel": {
                    "contentId": f"vid_{i}",
                    "metadata": {
                        "lockupMetadataViewModel": {
                            "title": {"content": f"Video {i}"},
                        }
                    },
                }
            }
        )
    items.append(
        {
            "continuationItemRenderer": {
                "continuationEndpoint": {
                    "continuationCommand": {"token": "token_after_20"}
                }
            }
        }
    )

    raw_response = {
        "contents": {
            "twoColumnWatchNextResults": {
                "secondaryResults": {"secondaryResults": {"results": items}}
            }
        }
    }
    instance.responseSource = raw_response

    def mock_get_value(source, keys):
        curr = source
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return None
        return curr

    instance._get_value.side_effect = mock_get_value

    res = SuggestionsService.fetch_related(
        "https://www.youtube.com/watch?v=initial_vid", limit=20
    )
    assert len(res["videos"]) == 20
    assert res["continuation"] == "token_after_20"


@patch("media_player.suggestions_service.RelatedVideosCore")
def test_fetch_related_with_continuation_pagination(mock_core_cls):
    instance = mock_core_cls.return_value
    instance._make_request = AsyncMock()

    raw_response = {
        "onResponseReceivedEndpoints": [
            {
                "appendContinuationItemsAction": {
                    "continuationItems": [
                        {
                            "lockupViewModel": {
                                "contentId": "paginated_vid_1",
                                "metadata": {
                                    "lockupMetadataViewModel": {
                                        "title": {"content": "Paginated Video 1"},
                                    }
                                },
                            }
                        },
                        {
                            "continuationItemRenderer": {
                                "continuationEndpoint": {
                                    "continuationCommand": {
                                        "token": "next_page_token_789"
                                    }
                                }
                            }
                        },
                    ]
                }
            }
        ]
    }
    instance.responseSource = raw_response

    def mock_get_value(source, keys):
        curr = source
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return None
        return curr

    instance._get_value.side_effect = mock_get_value

    res = SuggestionsService.fetch_related(
        "https://www.youtube.com/watch?v=original_vid",
        limit=10,
        continuation="token_123",
    )
    assert instance.continuationKey == "token_123"
    assert len(res["videos"]) == 1
    assert res["videos"][0]["id"] == "paginated_vid_1"
    assert res["videos"][0]["title"] == "Paginated Video 1"
    assert res["continuation"] == "next_page_token_789"


@patch("media_player.suggestions_service.RelatedVideosCore")
def test_fetch_related_event_loop_cleanup(mock_core_cls):
    import asyncio

    instance = mock_core_cls.return_value
    instance._make_request = AsyncMock()
    instance.responseSource = {}
    instance._get_value.return_value = []

    SuggestionsService.fetch_related("https://www.youtube.com/watch?v=test_vid")

    # Verify no closed event loop is left attached to current thread
    try:
        loop = asyncio.get_event_loop()
        assert not loop.is_closed()
    except RuntimeError:
        pass
