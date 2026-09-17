"""Tests for speech and screen reader client integration via Prism."""

import os
from unittest.mock import MagicMock, patch

import pytest

import speech_client


@pytest.fixture
def isolated_backend(monkeypatch):
    monkeypatch.setattr(speech_client, "_context", None)
    monkeypatch.setattr(speech_client, "_backend", None)
    monkeypatch.setattr(speech_client, "_initialized", False)


@pytest.fixture
def live_speech_backend(isolated_backend):
    return speech_client.get_backend()


def test_default_backend_is_mocked(mock_speech_backend):
    assert speech_client.get_backend() is mock_speech_backend
    speech_client.speak("Unit test announcement", interrupt=True)
    mock_speech_backend.speak.assert_called_once_with(
        "Unit test announcement", interrupt=True
    )
    speech_client.stop()
    mock_speech_backend.stop.assert_called_once_with()
    assert speech_client.is_speaking() is False
    speech_client.prism.Context.assert_not_called()


def test_reset_keeps_backend_initialization_mocked(mock_speech_backend):
    speech_client.reset()
    assert speech_client.get_backend() is mock_speech_backend
    speech_client.prism.Context.assert_called_once_with()
    speech_client.prism.Context.return_value.acquire_best.assert_called_once_with()


def test_speech_client_get_backend(monkeypatch, isolated_backend):
    prism = MagicMock()
    backend = prism.Context.return_value.acquire_best.return_value
    monkeypatch.setattr(speech_client, "prism", prism)

    assert speech_client.get_backend() is backend
    assert speech_client.get_backend() is backend
    prism.Context.assert_called_once_with()
    prism.Context.return_value.acquire_best.assert_called_once_with()


def test_speech_client_without_prism(monkeypatch, isolated_backend):
    monkeypatch.setattr(speech_client, "prism", None)

    assert speech_client.get_backend() is None
    assert speech_client._initialized is True


def test_speech_client_without_audio_backend(monkeypatch, isolated_backend):
    prism = MagicMock()
    prism.Context.return_value.acquire_best.return_value = None
    monkeypatch.setattr(speech_client, "prism", prism)

    assert speech_client.get_backend() is None
    speech_client.speak("No audio device")
    speech_client.stop()
    assert speech_client.is_speaking() is False
    prism.Context.return_value.acquire_best.assert_called_once_with()


def test_speech_client_backend_initialization_failure(monkeypatch, isolated_backend):
    prism = MagicMock()
    prism.Context.side_effect = RuntimeError("No speech service")
    monkeypatch.setattr(speech_client, "prism", prism)

    assert speech_client.get_backend() is None
    assert speech_client.get_backend() is None
    prism.Context.assert_called_once_with()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("HEXPLAYER_TEST_LIVE_SPEECH") != "1",
    reason="Set HEXPLAYER_TEST_LIVE_SPEECH=1 with a working speech backend",
)
def test_speech_client_live_backend(live_speech_backend):
    assert live_speech_backend is not None
    assert callable(live_speech_backend.speak)
    assert not isinstance(live_speech_backend, MagicMock)


def test_prism_import_and_native_components():
    from prism import _native, _prism_cffi

    assert hasattr(_prism_cffi, "lib")
    assert hasattr(_prism_cffi, "ffi")
    assert _native._find_native_dir() is not None


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


def test_speech_client_handles_prism_exceptions():
    with patch.object(speech_client, "get_backend") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.speak.side_effect = RuntimeError("Speech error")
        mock_get_backend.return_value = mock_backend

        # Should not raise exception
        speech_client.speak("Error test")
