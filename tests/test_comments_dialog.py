from unittest.mock import MagicMock

from gui.comments_dialog import CommentReplyDialog, CommentsDialog, format_comment_item


def test_format_comment_item_with_vote_status():
    comment_liked = {
        "author": "User1",
        "content": "Great video",
        "published_time": "1 hour ago",
        "likes": 10,
        "replies": 2,
        "is_liked": True,
        "is_disliked": False,
    }
    formatted_liked = format_comment_item(comment_liked)
    assert "أعجبك" in formatted_liked

    comment_disliked = {
        "author": "User2",
        "content": "Not good",
        "published_time": "2 hours ago",
        "likes": 0,
        "replies": 0,
        "is_liked": False,
        "is_disliked": True,
    }
    formatted_disliked = format_comment_item(comment_disliked)
    assert "لم يعجبك" in formatted_disliked

    comment_neutral = {
        "author": "User3",
        "content": "Neutral",
        "published_time": "3 hours ago",
        "likes": 5,
        "replies": 1,
        "is_liked": False,
        "is_disliked": False,
    }
    formatted_neutral = format_comment_item(comment_neutral)
    assert "أعجبك" not in formatted_neutral
    assert "لم يعجبك" not in formatted_neutral


def test_update_comments_disabled_comments_hides_controls(monkeypatch):
    dialog = CommentsDialog.__new__(CommentsDialog)
    dialog.commentLabel = MagicMock()
    dialog.commentTextCtrl = MagicMock()
    dialog.postCommentButton = MagicMock()
    dialog.loadMoreButton = MagicMock()
    dialog.commentsList = MagicMock()
    dialog.Layout = MagicMock()

    spoken = []
    monkeypatch.setattr("gui.comments_dialog.speak", lambda msg: spoken.append(msg))

    data = {"is_disabled": True, "comments": [], "continuation": None}
    dialog.update_comments(data)

    dialog.commentLabel.Hide.assert_called_once()
    dialog.commentTextCtrl.Hide.assert_called_once()
    dialog.postCommentButton.Hide.assert_called_once()
    dialog.loadMoreButton.Hide.assert_called_once()
    dialog.commentsList.Set.assert_called_once_with(["التعليقات معطلة لهذا الفيديو"])
    assert spoken == ["التعليقات معطلة لهذا الفيديو"]
    assert dialog.comments == []


def test_update_vote_result_updates_comment_and_list(monkeypatch):
    dialog = CommentsDialog.__new__(CommentsDialog)
    comment = {
        "id": "c1",
        "author": "User1",
        "content": "Test comment",
        "likes": 5,
        "is_liked": False,
        "is_disliked": False,
    }
    dialog.comments = [comment]
    dialog.commentsList = MagicMock()

    spoken = []
    monkeypatch.setattr("gui.comments_dialog.speak", lambda msg: spoken.append(msg))

    # Action like success
    dialog.update_vote_result(comment, "like", {"success": True})
    assert comment["is_liked"] is True
    assert comment["is_disliked"] is False
    assert spoken == ["تم الإعجاب بالتعليق"]
    dialog.commentsList.SetString.assert_called_once()

    # Action dislike success
    dialog.update_vote_result(comment, "dislike", {"success": True})
    assert comment["is_liked"] is False
    assert comment["is_disliked"] is True

    # Action remove_like success
    dialog.update_vote_result(comment, "remove_like", {"success": True})
    assert comment["is_liked"] is False
    assert comment["is_disliked"] is False


def test_update_vote_result_failure_shows_error(monkeypatch):
    dialog = CommentsDialog.__new__(CommentsDialog)
    comment = {"id": "c1", "is_liked": False, "is_disliked": False}
    dialog.comments = [comment]

    errors = []
    spoken = []
    monkeypatch.setattr(
        "gui.comments_dialog.utils.show_error",
        lambda msg, parent=None: errors.append(msg),
    )
    monkeypatch.setattr("gui.comments_dialog.speak", lambda msg: spoken.append(msg))

    dialog.update_vote_result(
        comment, "like", {"success": False, "error": "Failed to like"}
    )

    assert comment["is_liked"] is False
    assert errors == ["Failed to like"]
    assert spoken == ["Failed to like"]


def test_on_comment_vote_spawns_thread(monkeypatch):
    dialog = CommentsDialog.__new__(CommentsDialog)
    dialog.video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    comment = {"id": "c1"}

    called = []

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("gui.comments_dialog.Thread", ImmediateThread)
    monkeypatch.setattr(
        "gui.comments_dialog.utils.like_comment",
        lambda url, cid, act: ("like_comment", cid, act),
    )
    monkeypatch.setattr(
        "gui.comments_dialog.wx.CallAfter", lambda fn, *args: called.append(args)
    )

    dialog.onCommentVote(comment, "like")

    assert called == [(comment, "like", ("like_comment", "c1", "like"))]


def test_comment_reply_dialog_on_post_reply_empty_text(monkeypatch):
    dialog = CommentReplyDialog.__new__(CommentReplyDialog)
    dialog.posting = False
    dialog.replyTextCtrl = MagicMock()
    dialog.replyTextCtrl.Value = "   "

    spoken = []
    monkeypatch.setattr("gui.comments_dialog.speak", lambda msg: spoken.append(msg))

    dialog.onPostReply()

    assert spoken == ["يرجى كتابة رد قبل النشر"]
    dialog.replyTextCtrl.SetFocus.assert_called_once()
