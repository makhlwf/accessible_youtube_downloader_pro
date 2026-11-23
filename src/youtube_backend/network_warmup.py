"""Background DNS warmup for YouTube hosts."""

import socket
import threading


def prefetch_dns():
    """Warms up the DNS cache for common YouTube video host patterns."""
    hosts = [
        "www.youtube.com",
        "m.youtube.com",
        "i.ytimg.com",
        "yt3.ggpht.com",
        "googlevideo.com",
    ]
    for host in hosts:
        try:
            threading.Thread(
                target=socket.gethostbyname, args=(host,), daemon=True
            ).start()
        except Exception:
            pass
