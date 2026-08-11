from unittest.mock import patch


def test_get_video_comments_normalizes_response():
    from utils import get_video_comments

    with (
        patch("utils.config_get", return_value="cookies.txt"),
        patch("utils.deno_service") as mock_deno_service,
    ):
        mock_deno_service.send_command.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "parent_id": "",
                    "author": "User",
                    "content": "Hello",
                    "published_time": "2 days ago",
                    "likes": "1.2K",
                    "replies": "3",
                    "has_replies": True,
                    "reply_token": "token-1",
                }
            ],
            "continuation": "next-1",
        }

        result = get_video_comments("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result == {
        "comments": [
            {
                "id": "c1",
                "parent_id": "",
                "author": "User",
                "content": "Hello",
                "published_time": "2 days ago",
                "likes": 1200,
                "replies": 3,
                "has_replies": True,
                "reply_token": "token-1",
                "is_liked": False,
                "is_disliked": False,
            }
        ],
        "continuation": "next-1",
        "is_disabled": False,
    }
    mock_deno_service.send_command.assert_called_once_with(
        "get_video_comments",
        {
            "cookiesPath": "cookies.txt",
            "videoId": "dQw4w9WgXcQ",
            "continuationToken": None,
            "sortBy": "TOP_COMMENTS",
        },
    )


def test_get_comment_replies_sends_reply_token_and_continuation():
    from utils import get_comment_replies

    with patch("utils.deno_service") as mock_deno_service:
        mock_deno_service.send_command.return_value = {
            "comments": [{"author": "Reply User", "content": "Reply"}],
            "continuation": None,
        }

        result = get_comment_replies(
            "reply-token",
            continuation="more-token",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            parent_id="c1",
        )

    assert result["comments"][0]["author"] == "Reply User"
    mock_deno_service.send_command.assert_called_once_with(
        "get_comment_replies",
        {"replyToken": "reply-token", "continuationToken": "more-token"},
    )


def test_post_video_comment_sends_text_with_configured_cookies():
    from utils import post_video_comment

    with (
        patch("utils.config_get", return_value="cookies.txt"),
        patch("utils.os.path.exists", return_value=True),
        patch("utils.deno_service") as mock_deno_service,
    ):
        mock_deno_service.send_command.return_value = {"success": True}

        result = post_video_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "  Great video  ",
        )

    assert result == {"success": True, "error": None}
    mock_deno_service.send_command.assert_called_once_with(
        "post_video_comment",
        {
            "cookiesPath": "cookies.txt",
            "videoId": "dQw4w9WgXcQ",
            "text": "Great video",
        },
    )


def test_post_video_comment_requires_valid_cookies():
    from utils import post_video_comment

    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=False),
        patch("utils.deno_service") as mock_deno_service,
    ):
        result = post_video_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "Great video",
        )

    assert result["success"] is False
    assert "كوكيز" in result["error"]
    mock_deno_service.send_command.assert_not_called()


def test_post_video_comment_requires_deno():
    from utils import post_video_comment

    with (
        patch("utils.ensure_deno_installed", return_value=False),
        patch("utils.deno_service") as mock_deno_service,
    ):
        result = post_video_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "Great video",
        )

    assert result["success"] is False
    assert "Deno" in result["error"]
    mock_deno_service.send_command.assert_not_called()


def test_get_comment_replies_falls_back_to_yt_dlp_parent_filter(monkeypatch):
    import utils
    from utils import get_comment_replies

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {
                "comments": [
                    {
                        "id": "reply-1",
                        "parent": "parent-1",
                        "author": "Reply User",
                        "text": "A reply",
                        "_time_text": "1 hour ago",
                        "like_count": 4,
                    },
                    {
                        "id": "other",
                        "parent": "other-parent",
                        "author": "Other",
                        "text": "Other reply",
                    },
                ]
            }

    monkeypatch.setattr(utils, "YoutubeDL", FakeYoutubeDL)
    with (
        patch("utils.config_get", return_value=""),
        patch("utils.deno_service") as mock_deno_service,
    ):
        mock_deno_service.send_command.return_value = {"comments": []}

        result = get_comment_replies(
            "reply-token",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            parent_id="parent-1",
        )

    assert result == {
        "comments": [
            {
                "id": "reply-1",
                "parent_id": "parent-1",
                "author": "Reply User",
                "content": "A reply",
                "published_time": "1 hour ago",
                "likes": 4,
                "replies": 0,
                "has_replies": False,
                "reply_token": None,
                "is_liked": False,
                "is_disliked": False,
            }
        ],
        "continuation": None,
    }


def test_format_comment_item_contains_accessible_metadata():
    from gui.comments_dialog import format_comment_item

    row = format_comment_item(
        {
            "author": "User",
            "content": "Great\nvideo",
            "published_time": "1 day ago",
            "likes": 5,
            "replies": 2,
        }
    )

    assert row.startswith("التعليق: Great video")
    assert "User" in row
    assert "1 day ago" in row
    assert "5" in row
    assert "2" in row
    assert "Great video" in row


def test_copy_comment_copies_selected_content(monkeypatch):
    from gui import comments_dialog

    dialog = comments_dialog.CommentsDialog.__new__(comments_dialog.CommentsDialog)
    dialog.comments = [{"content": "Original\ncomment content"}]

    class FakeList:
        def GetSelection(self):
            return 0

    copied = {}
    spoken = []
    dialog.commentsList = FakeList()
    monkeypatch.setattr(
        comments_dialog.utils,
        "copy_to_clipboard",
        lambda content: copied.setdefault("content", content),
    )
    monkeypatch.setattr(
        comments_dialog, "speak", lambda message: spoken.append(message)
    )

    dialog.onCopyComment()

    assert copied["content"] == "Original\ncomment content"
    assert spoken == ["تم نسخ نص التعليق"]


def test_prepend_posted_comment_updates_accessible_list():
    from gui.comments_dialog import CommentsDialog

    dialog = CommentsDialog.__new__(CommentsDialog)
    dialog.comments = []

    class FakeList:
        def __init__(self):
            self.items = []
            self.selection = None
            self.focused = False

        def Set(self, items):
            self.items = items

        def SetSelection(self, selection):
            self.selection = selection

        def SetFocus(self):
            self.focused = True

    dialog.commentsList = FakeList()

    dialog._prepend_posted_comment("Posted from cookies")

    assert dialog.comments[0]["content"] == "Posted from cookies"
    assert dialog.comments[0]["author"] == "أنت"
    assert dialog.commentsList.selection == 0
    assert dialog.commentsList.focused is True
    assert "Posted from cookies" in dialog.commentsList.items[0]


def test_activate_comment_with_timestamp_calls_seek_callback():
    from gui.comments_dialog import CommentsDialog

    dialog = CommentsDialog.__new__(CommentsDialog)
    dialog.comments = [{"content": "The 2:47 thing was cool"}]
    calls = []
    dialog.timestamp_callback = lambda seconds, label: calls.append((seconds, label))

    class FakeList:
        def GetSelection(self):
            return 0

    dialog.commentsList = FakeList()

    dialog.onActivateComment()

    assert calls == [(167, "2:47")]


def test_normalize_comment_item_includes_liked_and_disliked_flags():
    from utils import _normalize_comment_item

    item = {
        "id": "c123",
        "parent_id": "",
        "author": "Tester",
        "content": "Nice!",
        "published_time": "1 hour ago",
        "likes": 10,
        "replies": 0,
        "has_replies": False,
        "reply_token": None,
        "is_liked": True,
        "is_disliked": False,
    }
    normalized = _normalize_comment_item(item)
    assert normalized["is_liked"] is True
    assert normalized["is_disliked"] is False

    item_defaults = {"id": "c456"}
    normalized_defaults = _normalize_comment_item(item_defaults)
    assert normalized_defaults["is_liked"] is False
    assert normalized_defaults["is_disliked"] is False


def test_normalize_comments_response_includes_is_disabled_flag():
    from utils import _normalize_comments_response

    resp = {
        "comments": [{"id": "c1", "content": "Hi"}],
        "continuation": None,
        "is_disabled": True,
    }
    normalized = _normalize_comments_response(resp)
    assert normalized["is_disabled"] is True
    assert len(normalized["comments"]) == 1

    resp_enabled = {"comments": [], "continuation": None}
    normalized_enabled = _normalize_comments_response(resp_enabled)
    assert normalized_enabled["is_disabled"] is False


def test_like_comment_sends_command_and_validates():
    from utils import like_comment

    # Validation: missing Deno
    with patch("utils.ensure_deno_installed", return_value=False):
        res_no_deno = like_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", action="like"
        )
        assert res_no_deno["success"] is False
        assert "Deno" in res_no_deno["error"]

    # Validation: missing cookies
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=False),
    ):
        res_no_cookie = like_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", action="like"
        )
        assert res_no_cookie["success"] is False
        assert "كوكيز" in res_no_cookie["error"]

    # Validation: missing comment_id
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
    ):
        res_no_id = like_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "", action="like"
        )
        assert res_no_id["success"] is False
        assert "معرف التعليق" in res_no_id["error"]

    # Success call
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
        patch("utils.config_get", return_value="cookies.txt"),
        patch("utils.deno_service") as mock_deno_service,
    ):
        mock_deno_service.send_command.return_value = {"success": True}
        res = like_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", action="like"
        )

    assert res == {"success": True}
    mock_deno_service.send_command.assert_called_once_with(
        "like_comment",
        {
            "cookiesPath": "cookies.txt",
            "videoId": "dQw4w9WgXcQ",
            "commentId": "c123",
            "action": "like",
        },
    )


def test_reply_to_comment_sends_command_and_validates():
    from utils import reply_to_comment

    # Validation: missing Deno
    with patch("utils.ensure_deno_installed", return_value=False):
        res_no_deno = reply_to_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", "My reply"
        )
        assert res_no_deno["success"] is False
        assert "Deno" in res_no_deno["error"]

    # Validation: missing cookies
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=False),
    ):
        res_no_cookie = reply_to_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", "My reply"
        )
        assert res_no_cookie["success"] is False
        assert "كوكيز" in res_no_cookie["error"]

    # Validation: missing comment_id
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
    ):
        res_no_id = reply_to_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "", "My reply"
        )
        assert res_no_id["success"] is False
        assert "معرف التعليق" in res_no_id["error"]

    # Validation: empty text
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
    ):
        res_no_text = reply_to_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", "   "
        )
        assert res_no_text["success"] is False
        assert "رد" in res_no_text["error"]

    # Success call
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
        patch("utils.config_get", return_value="cookies.txt"),
        patch("utils.deno_service") as mock_deno_service,
    ):
        mock_deno_service.send_command.return_value = {"success": True}
        res = reply_to_comment(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "c123", "My reply"
        )

    assert res == {"success": True}
    mock_deno_service.send_command.assert_called_once_with(
        "reply_to_comment",
        {
            "cookiesPath": "cookies.txt",
            "videoId": "dQw4w9WgXcQ",
            "commentId": "c123",
            "text": "My reply",
        },
    )
