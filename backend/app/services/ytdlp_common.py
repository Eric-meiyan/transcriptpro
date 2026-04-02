"""Common yt-dlp arguments shared across all services."""

from app.config import settings


def get_ytdlp_base_args() -> list[str]:
    """Return base yt-dlp args that should be included in ALL calls.
    
    Includes:
    - Proxy (if configured)
    - --remote-components ejs:npm (deno JS challenge solver)
    - --legacy-server-connect (SSL compatibility with some proxies)
    """
    args = []

    if settings.ytdlp_proxy:
        args.extend(["--proxy", settings.ytdlp_proxy])

    # Required for YouTube JS challenge solving (needs deno installed)
    args.extend(["--remote-components", "ejs:npm"])

    # Fix SSL handshake failures with some proxies
    args.append("--legacy-server-connect")

    return args
