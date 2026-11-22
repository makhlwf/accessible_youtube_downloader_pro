from unittest.mock import Mock

from gui import activity_dialog


def test_late_loading_result_is_ignored_after_cancel(monkeypatch):
    dialog = activity_dialog.LoadingDialog.__new__(activity_dialog.LoadingDialog)
    dialog._finished = False
    dialog.res = None
    dialog.EndModal = Mock()
    dialog.function = lambda: "late result"
    dialog.args = ()
    dialog.kwargs = {}
    dispatch = Mock()
    monkeypatch.setattr(activity_dialog.wx, "CallAfter", dispatch)

    dialog.run()
    assert dialog.res is None
    dialog.onClose(None)
    callback, *args = dispatch.call_args.args
    callback(*args)

    dialog.EndModal.assert_called_once_with(activity_dialog.wx.ID_CANCEL)
    assert dialog.res is None
    assert dialog.cancelled
