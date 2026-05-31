"""Shared HTZone / Arbitrip session authentication checks."""
from __future__ import annotations

PROFILE_URL = "https://api.arbitrip.com/profile"
START_URL = "https://htzone.arbitrip.com/"

_ANALYTICS_COOKIES = frozenset(
    {
        "CLID",
        "_CLCK",
        "_CLSK",
        "_GA",
        "_GID",
        "_FBP",
        "MUID",
        "SM",
        "TEST_COOKIE",
        "_EVGA_7110",
        "_SFID_BDDB",
    }
)

_AUTH_COOKIE_NAMES = frozenset({"PHPSESSID", "WGID", "JSESSIONID"})
_AUTH_DOMAINS = ("htzone.co.il", "tripzone.co.il", "arbitrip.com")
_SKIP_DOMAINS = ("clarity.ms", "doubleclick.net", "facebook.net", "outbrain.com", "c.clarity.ms")


def is_login_page(url: str) -> bool:
    u = url.lower()
    return "login" in u and "htzone.co.il" in u


def auth_cookie_names(cookies: list[dict]) -> list[str]:
    found: list[str] = []
    for cookie in cookies:
        name = cookie.get("name") or ""
        domain = (cookie.get("domain") or "").lower()
        if any(skip in domain for skip in _SKIP_DOMAINS):
            continue
        if not any(d in domain for d in _AUTH_DOMAINS):
            continue
        upper = name.upper()
        if upper in _ANALYTICS_COOKIES:
            continue
        if upper in _AUTH_COOKIE_NAMES or "SESS" in upper:
            found.append(name)
    return found


def profile_status(context) -> int | str:
    try:
        return context.request.get(PROFILE_URL, timeout=15000).status
    except Exception as exc:
        return f"error: {exc}"


def session_authenticated(context, page_url: str = "") -> tuple[bool, str]:
    """True only when profile API returns 200 or HTZone auth cookies are present off-login."""
    if page_url and is_login_page(page_url):
        status = profile_status(context)
        return False, f"on HTZone login page (profile={status})"

    status = profile_status(context)
    if status == 200:
        return True, "profile API 200"

    names = auth_cookie_names(context.cookies())
    if names and page_url:
        u = page_url.lower()
        if "tripzone.co.il" in u:
            return True, f"auth cookies: {', '.join(names)} (tripzone)"
        if "htzone.co.il" in u and "login" not in u:
            return True, f"auth cookies: {', '.join(names)} (htzone)"
        return False, (
            f"auth cookies {', '.join(names)} but not on post-login page "
            f"(profile={status}, url={page_url[:60]})"
        )
    if names:
        return True, f"auth cookies: {', '.join(names)}"

    cookie_count = len(context.cookies())
    return False, f"profile={status}, no auth cookies ({cookie_count} cookies total)"


def session_status(context, page_url: str = "") -> str:
    ok, detail = session_authenticated(context, page_url)
    parts = [detail]
    if page_url:
        parts.append(f"url={page_url[:80]}")
    if is_login_page(page_url):
        parts.append("on login page")
    return "; ".join(parts)
