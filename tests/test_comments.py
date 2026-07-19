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
            }
        ],
        "continuation": "next-1",
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
        comments_dialog.pyperclip,
        "copy",
        lambda content: copied.setdefault("content", content),
    )
    monkeypatch.setattr(
        comments_dialog, "speak", lambda message: spoken.append(message)
    )

    dialog.onCopyComment()

    assert copied["content"] == "Original\ncomment content"
    assert spoken == ["تم نسخ نص التعليق"]
