from threading import Thread

import wx

import utils
from language_handler import _
from media_player.timecodes import extract_timecodes
from speech_client import speak
from theme_handler import apply_theme


def format_comment_item(comment):
    author = comment.get("author") or _("غير معروف")
    published_time = comment.get("published_time") or _("تاريخ غير معروف")
    likes = comment.get("likes", 0)
    replies = comment.get("replies", 0)
    content = " ".join(str(comment.get("content") or "").split())
    if not content:
        content = _("تعليق فارغ")

    formatted = _(
        "التعليق: {content}، المستخدم: {author}، التاريخ: {published_time}، "
        "الإعجابات: {likes}، الردود: {replies}"
    ).format(
        content=content,
        author=author,
        published_time=published_time,
        likes=likes,
        replies=replies,
    )
    if comment.get("is_liked"):
        formatted += _("، (أعجبك)")
    elif comment.get("is_disliked"):
        formatted += _("، (لم يعجبك)")
    return formatted


class CommentReplyDialog(wx.Dialog):
    def __init__(self, parent, video_url, target_comment):
        wx.Dialog.__init__(self, parent, title=_("رد على التعليق"), size=(600, 400))
        self.Centre()
        self.video_url = video_url
        self.target_comment = target_comment or {}
        self.posting = False

        panel = wx.Panel(self)
        author = self.target_comment.get("author") or _("غير معروف")
        snippet = " ".join(str(self.target_comment.get("content") or "").split())
        if len(snippet) > 100:
            snippet = snippet[:100] + "..."
        if not snippet:
            snippet = _("تعليق فارغ")

        target_label = wx.StaticText(
            panel,
            -1,
            _("الرد على {author}: {content}").format(author=author, content=snippet),
        )
        self.replyTextCtrl = wx.TextCtrl(
            panel,
            -1,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER,
            name="reply",
        )
        self.replyTextCtrl.SetMinSize((-1, 100))
        self.postButton = wx.Button(panel, -1, _("نشر الرد"))
        self.cancelButton = wx.Button(panel, wx.ID_CANCEL, _("إلغاء"))

        buttonsSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonsSizer.Add(self.postButton, 1)
        buttonsSizer.Add(self.cancelButton, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(target_label, 0, wx.ALL, 5)
        sizer.Add(self.replyTextCtrl, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(buttonsSizer, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(sizer)

        self.postButton.Bind(wx.EVT_BUTTON, self.onPostReply)
        self.cancelButton.Bind(wx.EVT_BUTTON, lambda event: self.Destroy())
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        self.Bind(wx.EVT_CLOSE, lambda event: self.Destroy())

        apply_theme(self)

    def onPostReply(self, event=None):
        if self.posting:
            return

        text = self.replyTextCtrl.Value.strip()
        if not text:
            speak(_("يرجى كتابة رد قبل النشر"))
            self.replyTextCtrl.SetFocus()
            return

        self.posting = True
        self.postButton.Disable()
        speak(_("جاري نشر الرد..."))

        def _post():
            result = utils.reply_to_comment(
                self.video_url,
                self.target_comment.get("id"),
                text,
                parent=self,
            )
            wx.CallAfter(self.update_reply_result, result)

        Thread(target=_post, daemon=True).start()

    def update_reply_result(self, result):
        self.posting = False
        self.postButton.Enable()

        if isinstance(result, dict) and result.get("success"):
            speak(_("تم نشر الرد بنجاح"))
            self.Destroy()
            return

        error_msg = (
            result.get("error")
            if isinstance(result, dict) and result.get("error")
            else utils.format_bilingual_message("تعذر نشر الرد", "Failed to post reply")
        )
        wx.MessageBox(
            error_msg,
            utils.format_bilingual_message("خطأ", "Error"),
            style=wx.OK | wx.ICON_ERROR,
            parent=self,
        )
        if self.replyTextCtrl:
            self.replyTextCtrl.SetFocus()
        speak(error_msg)

    def onCharHook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.Destroy()
            return
        if self.replyTextCtrl and wx.Window.FindFocus() == self.replyTextCtrl:
            if key == wx.WXK_RETURN and event.ControlDown():
                self.onPostReply()
                return
            event.Skip()
            return
        event.Skip()


class CommentsDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        video_url=None,
        title=None,
        reply_token=None,
        parent_comment_id=None,
        timestamp_callback=None,
    ):
        dialog_title = _("ردود التعليق") if reply_token else _("تعليقات الفيديو")
        wx.Dialog.__init__(self, parent, title=dialog_title, size=(800, 500))
        self.Centre()
        self.video_url = video_url
        self.source_title = title or ""
        self.reply_token = reply_token
        self.parent_comment_id = parent_comment_id
        self.timestamp_callback = timestamp_callback
        self.comments = []
        self.continuation = None
        self.loading = False
        self.posting = False

        panel = wx.Panel(self)
        label_text = _("الردود:") if self.reply_token else _("التعليقات:")
        if self.source_title and not self.reply_token:
            label_text = _("تعليقات {}:").format(self.source_title)
        self.label = wx.StaticText(panel, -1, label_text)
        self.commentsList = wx.ListBox(panel, -1)
        self.timestampsPanel = wx.Panel(panel)
        self.timestampsSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.timestampsPanel.SetSizer(self.timestampsSizer)
        self.timestampsPanel.Hide()
        self.commentLabel = None
        self.commentTextCtrl = None
        self.postCommentButton = None
        if not self.reply_token:
            self.commentLabel = wx.StaticText(panel, -1, _("تعليق جديد:"))
            self.commentTextCtrl = wx.TextCtrl(
                panel,
                -1,
                style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER,
                name="comment",
            )
            self.commentTextCtrl.SetMinSize((-1, 80))
            self.postCommentButton = wx.Button(panel, -1, _("نشر التعليق"))
        self.loadMoreButton = wx.Button(panel, -1, _("تحميل المزيد"))
        self.closeButton = wx.Button(panel, wx.ID_CANCEL, _("إغلاق"))

        buttonsSizer = wx.BoxSizer(wx.HORIZONTAL)
        if self.postCommentButton:
            buttonsSizer.Add(self.postCommentButton, 1)
        buttonsSizer.Add(self.loadMoreButton, 1)
        buttonsSizer.Add(self.closeButton, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.label, 0, wx.ALL, 5)
        sizer.Add(self.commentsList, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(
            self.timestampsPanel,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            5,
        )
        if self.commentTextCtrl:
            sizer.Add(self.commentLabel, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
            sizer.Add(self.commentTextCtrl, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(buttonsSizer, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(sizer)

        self.loadMoreButton.Bind(wx.EVT_BUTTON, self.onLoadMore)
        if self.postCommentButton:
            self.postCommentButton.Bind(wx.EVT_BUTTON, self.onPostComment)
        self.closeButton.Bind(wx.EVT_BUTTON, lambda event: self.Destroy())
        self.commentsList.Bind(wx.EVT_LISTBOX, self.onCommentSelectionChanged)
        self.commentsList.Bind(wx.EVT_LISTBOX_DCLICK, self.onActivateComment)
        self.commentsList.Bind(wx.EVT_CONTEXT_MENU, self.onContextMenu)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        self.Bind(wx.EVT_CLOSE, lambda event: self.Destroy())

        apply_theme(self)
        self.load_comments()
        self.Show()

    def load_comments(self, load_more=False):
        if self.loading:
            return
        self.loading = True
        if not load_more:
            self.commentsList.Set([_("جاري تحميل التعليقات...")])
            speak(_("جاري تحميل التعليقات"))
        else:
            speak(_("جاري تحميل المزيد من التعليقات"))

        def _load():
            if self.reply_token:
                data = utils.get_comment_replies(
                    self.reply_token,
                    self.continuation if load_more else None,
                    video_url=self.video_url,
                    parent_id=self.parent_comment_id,
                )
            else:
                data = utils.get_video_comments(
                    self.video_url, self.continuation if load_more else None
                )
            wx.CallAfter(self.update_comments, data, load_more)

        Thread(target=_load, daemon=True).start()

    def update_comments(self, data, load_more=False):
        self.loading = False
        if isinstance(data, dict) and data.get("is_disabled"):
            if self.commentLabel:
                self.commentLabel.Hide()
            if self.commentTextCtrl:
                self.commentTextCtrl.Hide()
            if self.postCommentButton:
                self.postCommentButton.Hide()
            self.comments = []
            self.commentsList.Set([_("التعليقات معطلة لهذا الفيديو")])
            self.loadMoreButton.Hide()
            self.Layout()
            speak(_("التعليقات معطلة لهذا الفيديو"))
            return

        new_comments = data.get("comments", []) if isinstance(data, dict) else []
        self.continuation = data.get("continuation") if isinstance(data, dict) else None

        if load_more:
            self.comments.extend(new_comments)
        else:
            self.comments = new_comments

        if self.comments:
            self.commentsList.Set(
                [format_comment_item(comment) for comment in self.comments]
            )
            self.commentsList.SetSelection(0)
        else:
            message = (
                _("لا توجد ردود متاحة")
                if self.reply_token
                else _("لا توجد تعليقات متاحة")
            )
            self.commentsList.Set([message])
        self.update_timestamp_buttons()

        if self.continuation:
            self.loadMoreButton.Show()
        else:
            self.loadMoreButton.Hide()

        self.Layout()
        self.commentsList.SetFocus()
        speak(_("تم تحميل التعليقات"))

    def onLoadMore(self, event):
        if self.continuation:
            self.load_comments(load_more=True)

    def onPostComment(self, event=None):
        if self.reply_token or not self.commentTextCtrl or self.posting:
            return

        text = self.commentTextCtrl.Value.strip()
        if not text:
            speak(_("يرجى كتابة تعليق قبل النشر"))
            self.commentTextCtrl.SetFocus()
            return

        self.posting = True
        if self.postCommentButton:
            self.postCommentButton.Disable()
        speak(_("جاري نشر التعليق"))

        def _post():
            result = utils.post_video_comment(self.video_url, text, parent=self)
            wx.CallAfter(self.update_post_result, result, text)

        Thread(target=_post, daemon=True).start()

    def update_post_result(self, result, text):
        self.posting = False
        if self.postCommentButton:
            self.postCommentButton.Enable()

        if isinstance(result, dict) and result.get("success"):
            self.commentTextCtrl.SetValue("")
            self._prepend_posted_comment(text)
            speak(_("تم نشر التعليق"))
            return

        error_msg = (
            result.get("error")
            if isinstance(result, dict) and result.get("error")
            else utils.format_bilingual_message(
                "تعذر نشر التعليق", "Failed to post comment"
            )
        )
        wx.MessageBox(
            error_msg,
            utils.format_bilingual_message("خطأ", "Error"),
            style=wx.OK | wx.ICON_ERROR,
            parent=self,
        )
        if self.commentTextCtrl:
            self.commentTextCtrl.SetFocus()
        speak(error_msg)

    def _prepend_posted_comment(self, text):
        comment = {
            "id": "",
            "parent_id": "",
            "author": _("أنت"),
            "content": text,
            "published_time": _("الآن"),
            "likes": 0,
            "replies": 0,
            "has_replies": False,
            "reply_token": None,
        }
        self.comments.insert(0, comment)
        self.commentsList.Set([format_comment_item(item) for item in self.comments])
        self.commentsList.SetSelection(0)
        self.update_timestamp_buttons()
        self.commentsList.SetFocus()

    def onCommentSelectionChanged(self, event=None):
        self.update_timestamp_buttons()
        if event:
            event.Skip()

    def onOpenReplies(self, event=None):
        selection = self.commentsList.GetSelection()
        if selection == wx.NOT_FOUND or selection >= len(self.comments):
            return

        comment = self.comments[selection]
        if not comment.get("has_replies") or not comment.get("reply_token"):
            speak(_("لا توجد ردود لهذا التعليق"))
            return

        CommentsDialog(
            self,
            video_url=self.video_url,
            title=comment.get("author"),
            reply_token=comment["reply_token"],
            parent_comment_id=comment.get("id"),
            timestamp_callback=self.timestamp_callback,
        )

    def _selected_comment(self):
        selection = self.commentsList.GetSelection()
        if selection == wx.NOT_FOUND or selection >= len(self.comments):
            return None
        return self.comments[selection]

    def _comment_timestamps(self, comment):
        return extract_timecodes(comment.get("content") if comment else "")

    def update_timestamp_buttons(self):
        if not hasattr(self, "timestampsPanel"):
            return

        for child in self.timestampsPanel.GetChildren():
            child.Destroy()
        self.timestampsSizer.Clear()

        timestamps = self._comment_timestamps(self._selected_comment())
        if not timestamps:
            self.timestampsPanel.Hide()
            self.Layout()
            return

        for timestamp in timestamps:
            button = wx.Button(self.timestampsPanel, -1, timestamp["label"])
            button.SetName(_("وقت في التعليق"))
            button.Bind(
                wx.EVT_BUTTON,
                lambda event, value=timestamp: self.onJumpToTimestamp(
                    event, timestamp=value
                ),
            )
            self.timestampsSizer.Add(button, 0, wx.RIGHT, 5)
        self.timestampsPanel.Show()
        self.Layout()

    def onActivateComment(self, event=None):
        comment = self._selected_comment()
        timestamps = self._comment_timestamps(comment)
        if timestamps:
            self.onJumpToTimestamp(timestamp=timestamps[0])
            return
        self.onOpenReplies()

    def onJumpToTimestamp(self, event=None, timestamp=None):
        if timestamp is None:
            comment = self._selected_comment()
            timestamps = self._comment_timestamps(comment)
            timestamp = timestamps[0] if timestamps else None

        if timestamp is None:
            speak(_("لا توجد أوقات في هذا التعليق"))
            return

        if not self.timestamp_callback:
            speak(_("لا يوجد مشغل متاح للانتقال إلى الوقت"))
            return

        self.timestamp_callback(timestamp["seconds"], timestamp["label"])

    def onContextMenu(self, event):
        selection = self.commentsList.GetSelection()
        if selection == wx.NOT_FOUND or selection >= len(self.comments):
            return

        comment = self.comments[selection]
        menu = wx.Menu()

        for timestamp in self._comment_timestamps(comment):
            item = menu.Append(-1, _("الانتقال إلى {}").format(timestamp["label"]))
            self.Bind(
                wx.EVT_MENU,
                lambda event, value=timestamp: self.onJumpToTimestamp(
                    event, timestamp=value
                ),
                item,
            )

        like_item = menu.Append(-1, _("إعجاب بالتعليق"))
        self.Bind(
            wx.EVT_MENU,
            lambda event, c=comment: self.onCommentVote(c, "like"),
            like_item,
        )

        dislike_item = menu.Append(-1, _("عدم إعجاب بالتعليق"))
        self.Bind(
            wx.EVT_MENU,
            lambda event, c=comment: self.onCommentVote(c, "dislike"),
            dislike_item,
        )

        remove_like_item = menu.Append(-1, _("إلغاء التفاعل مع التعليق"))
        self.Bind(
            wx.EVT_MENU,
            lambda event, c=comment: self.onCommentVote(c, "remove_like"),
            remove_like_item,
        )

        reply_item = menu.Append(-1, _("رد على التعليق"))
        self.Bind(
            wx.EVT_MENU,
            lambda event, c=comment: self.onReplyToComment(c),
            reply_item,
        )

        if comment.get("has_replies") and comment.get("reply_token"):
            replies_item = menu.Append(-1, _("عرض الردود"))
            self.Bind(wx.EVT_MENU, self.onOpenReplies, replies_item)

        copy_item = menu.Append(-1, _("نسخ نص التعليق"))
        self.Bind(wx.EVT_MENU, self.onCopyComment, copy_item)

        self.commentsList.PopupMenu(menu)
        menu.Destroy()

    def onReplyToComment(self, comment=None):
        if comment is None:
            comment = self._selected_comment()
        if not comment:
            return
        dlg = CommentReplyDialog(self, self.video_url, comment)
        dlg.ShowModal()

    def onCommentVote(self, comment, action):
        if not comment or not comment.get("id"):
            return

        speak(_("جاري تحديث التفاعل..."))

        def _vote():
            result = utils.like_comment(
                self.video_url, comment["id"], action, parent=self
            )
            wx.CallAfter(self.update_vote_result, comment, action, result)

        Thread(target=_vote, daemon=True).start()

    def update_vote_result(self, comment, action, result):
        if isinstance(result, dict) and result.get("success"):
            if action == "like":
                comment["is_liked"] = True
                comment["is_disliked"] = False
                speak(_("تم الإعجاب بالتعليق"))
            elif action == "dislike":
                comment["is_liked"] = False
                comment["is_disliked"] = True
                speak(_("تم عدم الإعجاب بالتعليق"))
            elif action == "remove_like":
                comment["is_liked"] = False
                comment["is_disliked"] = False
                speak(_("تم إلغاء التفاعل مع التعليق"))

            try:
                idx = self.comments.index(comment)
                self.commentsList.SetString(idx, format_comment_item(comment))
            except ValueError:
                pass
        else:
            error_msg = (
                result.get("error")
                if isinstance(result, dict) and result.get("error")
                else utils.format_bilingual_message(
                    "حدث خطأ أثناء تنفيذ الإجراء على التعليق.",
                    "An error occurred while executing comment action.",
                )
            )
            wx.MessageBox(
                error_msg,
                utils.format_bilingual_message("خطأ", "Error"),
                style=wx.OK | wx.ICON_ERROR,
                parent=self,
            )
            speak(error_msg)

    def onCopyComment(self, event=None):
        selection = self.commentsList.GetSelection()
        if selection == wx.NOT_FOUND or selection >= len(self.comments):
            return

        utils.copy_to_clipboard(self.comments[selection].get("content") or "")
        speak(_("تم نسخ نص التعليق"))

    def onCharHook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.Destroy()
            return
        if self.commentTextCtrl and wx.Window.FindFocus() == self.commentTextCtrl:
            if key == wx.WXK_RETURN and event.ControlDown():
                self.onPostComment()
                return
            event.Skip()
            return
        if key == wx.WXK_RETURN:
            self.onActivateComment()
            return
        event.Skip()
