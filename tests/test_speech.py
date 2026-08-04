"""Tests for speech and screen reader client integration via Prism."""

from unittest.mock import MagicMock, patch

import nvda_client.client as nvda_compat
import speech_client


def test_speech_client_get_backend():
    backend = speech_client.get_backend()
    # On Windows test runners, Prism should successfully acquire a backend (e.g. OneCore/SAPI).
    assert backend is not None
    assert hasattr(backend, "speak")


def test_speak_handles_empty_or_whitespace():
    with patch.object(speech_client, "get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend

        speech_client.speak("")
        speech_client.speak("   ")
        speech_client.speak(None)

        mock_backend.speak.assert_not_called()


def test_speak_calls_prism_backend():
    with patch.object(speech_client, "get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend

        speech_client.speak("Hello world", interrupt=True)
        mock_backend.speak.assert_called_once_with("Hello world", interrupt=True)


def test_stop_calls_prism_backend():
    with patch.object(speech_client, "get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend

        speech_client.stop()
        mock_backend.stop.assert_called_once()


def test_is_speaking_returns_status():
    with patch.object(speech_client, "get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.speaking = True
        mock_get_backend.return_value = mock_backend

        assert speech_client.is_speaking() is True


def test_legacy_nvda_compat_exports():
    with patch.object(speech_client, "speak") as mock_speak:
        nvda_compat.speak("Test text")
        mock_speak.assert_called_once_with("Test text", interrupt=False)


def test_speech_client_handles_prism_exceptions():
    with patch.object(speech_client, "get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.speak.side_effect = RuntimeError("Speech error")
        mock_get_backend.return_value = mock_backend

        # Should not raise exception
        speech_client.speak("Error test")
