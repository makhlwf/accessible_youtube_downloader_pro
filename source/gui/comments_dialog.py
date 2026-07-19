from threading import Thread

import wx

import utils
from language_handler import _
from nvda_client.client import speak
from theme_handler import apply_theme


def format_comment_item(comment):
    author = comment.get("author") or _("غير معروف")
    published_time = comment.get("published_time") or _("تاريخ غير معروف")
    likes = comment.get("likes", 0)
    replies = comment.get("replies", 0)
    content = " ".join(str(comment.get("content") or "").split())
    if not content:
        content = _("تعليق فارغ")

    return _(
        "المستخدم: {author}، التاريخ: {published_time}، الإعجابات: {likes}، "
        "الردود: {replies}، التعليق: {content}"
    ).format(
        author=author,
        published_time=published_time,
        likes=likes,
        replies=replies,
        content=content,
    )


class CommentsDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        video_url=None,
        title=None,
        reply_token=None,
        parent_comment_id=None,
    ):
        dialog_title = _("ردود التعليق") if reply_token else _("تعليقات الفيديو")
        wx.Dialog.__init__(self, parent, title=dialog_title, size=(800, 500))
        self.Centre()
        self.video_url = video_url
        self.source_title = title or ""
        self.reply_token = reply_token
        self.parent_comment_id = parent_comment_id
        self.comments = []
        self.continuation = None
        self.loading = False

        panel = wx.Panel(self)
        label_text = _("الردود:") if self.reply_token else _("التعليقات:")
        if self.source_title and not self.reply_token:
            label_text = _("تعليقات {}:").format(self.source_title)
        self.label = wx.StaticText(panel, -1, label_text)
        self.commentsList = wx.ListBox(panel, -1)
        self.loadMoreButton = wx.Button(panel, -1, _("تحميل المزيد"))
        self.closeButton = wx.Button(panel, wx.ID_CANCEL, _("إغلاق"))

        buttonsSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonsSizer.Add(self.loadMoreButton, 1)
        buttonsSizer.Add(self.closeButton, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.label, 0, wx.ALL, 5)
        sizer.Add(self.commentsList, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(buttonsSizer, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(sizer)

        self.loadMoreButton.Bind(wx.EVT_BUTTON, self.onLoadMore)
        self.closeButton.Bind(wx.EVT_BUTTON, lambda event: self.Destroy())
        self.commentsList.Bind(wx.EVT_LISTBOX_DCLICK, self.onOpenReplies)
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
        )

    def onCharHook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.Destroy()
            return
        if key == wx.WXK_RETURN:
            self.onOpenReplies()
            return
        event.Skip()
