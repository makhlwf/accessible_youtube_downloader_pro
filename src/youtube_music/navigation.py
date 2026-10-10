"""A tiny back-stack of view controllers for the YouTube Music panel.

The panel reuses a single ``wx.ListBox``; navigating into an album/artist/
playlist pushes a new view controller, and Backspace/Alt+Left pops back to the
previous one. This keeps the "flip" feeling like the YouTube browser's
back-navigation without opening new windows.
"""


class ViewStack:
    def __init__(self):
        self._stack = []

    @property
    def current(self):
        return self._stack[-1] if self._stack else None

    def push(self, view):
        self._stack.append(view)
        return view

    def pop(self):
        """Remove and return the top view, unless it is the root (kept)."""
        if len(self._stack) > 1:
            return self._stack.pop()
        return None

    def reset(self, view):
        """Replace the whole stack with a single root view."""
        self._stack = [view]
        return view

    def clear(self):
        self._stack = []

    def can_go_back(self):
        return len(self._stack) > 1

    def __len__(self):
        return len(self._stack)
