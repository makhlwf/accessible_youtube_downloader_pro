import wx
from language_handler import _
import utils

class QualitySelectionDialog(wx.SingleChoiceDialog):
    def __init__(self, parent, qualities, audio_mode=False):
        if not audio_mode:
            message = _("Select the video quality you want to download:")
            title = _("Video Quality")
            choices = [utils.get_quality_description(q) for q in qualities]
        else:
            message = _("Select the audio quality you want to download:")
            title = _("Audio Quality")
            choices = [f"{q}kbps" for q in qualities]

        super().__init__(parent, message, title, choices)
        self.qualities = qualities

    def get_selected_quality(self):
        selection = self.GetSelection()
        if selection != wx.NOT_FOUND:
            return self.qualities[selection]
        return None
