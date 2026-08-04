"""Speech and Screen Reader interface powered by Prism (ethindp/prism)."""

import logging
import threading

try:
    import prism
except ImportError:
    prism = None

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_context: object | None = None
_backend: object | None = None
_initialized: bool = False


def get_backend() -> object | None:
    """Get or initialize the best available Prism screen reader / TTS backend."""
    global _context, _backend, _initialized
    if _initialized:
        return _backend

    with _lock:
        if _initialized:
            return _backend

        if prism is None:
            logger.warning("Prism library (prismatoid) is not available.")
            _initialized = True
            return None

        try:
            _context = prism.Context()
            _backend = _context.acquire_best()
            if _backend:
                logger.info(f"Initialized Prism speech backend: {_backend.name}")
            else:
                logger.warning("No suitable speech backend found via Prism.")
        except Exception as e:
            logger.warning(f"Failed to initialize Prism speech backend: {e}")
            _backend = None

        _initialized = True
        return _backend


def speak(msg: str, interrupt: bool = False) -> None:
    """Announce speech text via Prism.

    :param msg: The text message to be spoken.
    :param interrupt: If True, interrupts any ongoing speech before speaking.
    """
    if not msg or not str(msg).strip():
        return

    try:
        backend = get_backend()
        if backend:
            backend.speak(str(msg), interrupt=interrupt)
    except Exception as e:
        logger.warning(f"Prism speak error: {e}")


def stop() -> None:
    """Stop any currently ongoing speech."""
    try:
        backend = get_backend()
        if backend:
            backend.stop()
    except Exception as e:
        logger.warning(f"Prism stop error: {e}")


def is_speaking() -> bool:
    """Check if speech is currently active."""
    try:
        backend = get_backend()
        if backend:
            return getattr(backend, "speaking", False)
    except Exception as e:
        logger.warning(f"Prism is_speaking error: {e}")
    return False


def reset() -> None:
    """Reset cached backend state for testing (re-enables initialization without deleting C objects)."""
    global _initialized
    with _lock:
        _initialized = False
