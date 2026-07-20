import wx
from language_handler import _
from theme_handler import apply_theme
import utils


class QualitySelectionDialog(wx.SingleChoiceDialog):
    def __init__(self, parent, qualities, audio_mode=False):
        if not audio_mode:
            message = _("اختر جودة الفيديو التي تريد تنزيلها:")
            title = _("جودة الفيديو")
            choices = [utils.get_quality_description(q) for q in qualities]
        else:
            message = _("اختر جودة الصوت التي تريد تنزيلها:")
            title = _("جودة الصوت")
            choices = [f"{q}{_('ك.ب/ث')}" for q in qualities]

        super().__init__(parent, message, title, choices)
        self.qualities = qualities
        apply_theme(self)

    def get_selected_quality(self):
        selection = self.GetSelection()
        if selection != wx.NOT_FOUND:
            return self.qualities[selection]
        return None
