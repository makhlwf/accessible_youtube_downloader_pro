"""Typed errors and a normalising decorator for the YouTube Music subsystem.

Views depend on these distinct error types to decide how to react: an
``AuthRequiredError`` prompts the user to sign in (import browser cookies),
while a ``YTMusicUnavailableError`` surfaces a retryable error row. Raw
exceptions from ytmusicapi/network are funnelled through :func:`guard`.
"""

import functools
import logging

logger = logging.getLogger(__name__)


class YTMusicError(Exception):
    """Base class for all YouTube Music subsystem errors."""


class AuthRequiredError(YTMusicError):
    """An operation needs a signed-in account but none is available.

    Raised when there are no cookies, the cookies lack auth tokens, or the
    server rejects the request as unauthorized (expired cookies).
    """


class YTMusicUnavailableError(YTMusicError):
    """A request failed for a non-auth reason (network, malformed response)."""


class EmptyResultError(YTMusicError):
    """A request succeeded but produced no usable items."""


# Substrings that mark an authorization failure in a raw exception message.
_AUTH_MARKERS = ("401", "403", "unauthorized", "not authenticated", "sign in", "login")


def guard(func):
    """Wrap a service method so raw exceptions become typed subsystem errors.

    Authorization failures become :class:`AuthRequiredError`; every other
    failure becomes :class:`YTMusicUnavailableError`. The original exception is
    logged with a traceback (never any cookie or credential values) and chained.
    Already-typed :class:`YTMusicError` instances pass through untouched.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except YTMusicError:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if any(marker in message for marker in _AUTH_MARKERS):
                logger.warning(
                    "YouTube Music auth failure in %s", func.__name__, exc_info=True
                )
                raise AuthRequiredError(str(exc)) from exc
            logger.exception("YouTube Music request failed in %s", func.__name__)
            raise YTMusicUnavailableError(str(exc)) from exc

    return wrapper
