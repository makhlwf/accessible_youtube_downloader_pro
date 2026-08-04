"""Legacy compatibility module forwarding speech calls to speech_client (Prism)."""

import speech_client


def speak(msg, interrupt=False):
    return speech_client.speak(msg, interrupt=interrupt)


def stop():
    return speech_client.stop()


def is_speaking():
    return speech_client.is_speaking()


def get_backend():
    return speech_client.get_backend()


__all__ = ["get_backend", "is_speaking", "speak", "stop"]
