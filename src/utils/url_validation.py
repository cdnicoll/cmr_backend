"""URL validation: SSRF protection, normalization, and type detection."""
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse, urlunparse

# Blocked: localhost, 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, link-local
PRIVATE_NETWORKS = (
    "127.0.0.0/8",  # Loopback
    "10.0.0.0/8",  # RFC 1918
    "172.16.0.0/12",  # RFC 1918
    "192.168.0.0/16",  # RFC 1918
    "169.254.0.0/16",  # Link-local
    "::1/128",  # IPv6 loopback
    "fc00::/7",  # IPv6 unique local
    "fe80::/10",  # IPv6 link-local
)

BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
)

ALLOWED_SCHEMES = frozenset({"http", "https"})

# YouTube patterns: youtube.com/watch, youtu.be/
YOUTUBE_DOMAINS = frozenset({"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"})


@dataclass
class ValidationResult:
    """Result of URL validation."""

    valid: bool
    normalized_url: str | None
    resource_type: str  # "website" or "youtube"
    error: str | None = None


def _is_private_ip(host: str) -> bool:
    """Check if host resolves to a private/internal IP."""
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback or addr.is_private or addr.is_link_local:
        return True
    if addr.is_reserved:
        return True
    return False


def _is_blocked_hostname(host: str) -> bool:
    """Check if hostname is in blocked list (localhost, etc.)."""
    return host.lower() in BLOCKED_HOSTNAMES


def _normalize_url(url: str) -> str:
    """Normalize URL: prefer https, remove trailing slash for consistency."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    if scheme not in ALLOWED_SCHEMES:
        scheme = "https"
    netloc = parsed.netloc.lower() if parsed.netloc else ""
    path = parsed.path.rstrip("/") or "/"
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized


def _detect_resource_type(netloc: str, path: str) -> str:
    """Detect resource type: youtube or website."""
    domain = netloc.lower().replace("www.", "")
    if domain in YOUTUBE_DOMAINS:
        return "youtube"
    if domain == "youtube.com" or domain == "youtu.be":
        return "youtube"
    return "website"


def _validate_youtube_format(url: str, parsed) -> str | None:
    """Validate YouTube URL format. Returns error message or None if valid."""
    netloc = parsed.netloc.lower() if parsed.netloc else ""
    path = parsed.path or "/"
    domain = netloc.replace("www.", "")

    if domain == "youtu.be":
        # youtu.be/VIDEO_ID - path should be /something
        if not path or path == "/" or len(path) < 2:
            return "Invalid youtu.be URL: missing video ID"
        return None

    if "youtube.com" in domain:
        # youtube.com/watch?v=VIDEO_ID
        if "/watch" in path and "v=" in (parsed.query or ""):
            return None
        if "/shorts/" in path:
            return None
        return "Invalid YouTube URL: expected youtube.com/watch?v=... or youtu.be/VIDEO_ID"

    return None


def validate_url(url: str) -> ValidationResult:
    """
    Validate URL: SSRF protection, normalization, type detection.
    Returns ValidationResult with valid, normalized_url, resource_type, and optional error.
    """
    if not url or not isinstance(url, str):
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error="URL is required",
        )

    url = url.strip()
    if not url:
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error="URL is required",
        )

    try:
        parsed = urlparse(url)
    except Exception as e:
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error=f"Invalid URL: {e!s}",
        )

    # Scheme check
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error=f"Unsupported scheme: {scheme or '(none)'}. Use http or https.",
        )

    # Need netloc for host validation
    netloc = parsed.netloc or ""
    if not netloc:
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error="Invalid URL: missing host",
        )

    # Extract host (remove port)
    host = netloc.split(":")[0]

    # Block localhost by hostname
    if _is_blocked_hostname(host):
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error="URL blocked: localhost not allowed (SSRF protection)",
        )

    # Block private/internal IPs
    if _is_private_ip(host):
        return ValidationResult(
            valid=False,
            normalized_url=None,
            resource_type="website",
            error="URL blocked: internal/private IP not allowed (SSRF protection)",
        )

    # Try to resolve hostname to IP and check (for hostnames that resolve to private IPs)
    try:
        import socket

        resolved = socket.gethostbyname(host)
        if _is_private_ip(resolved):
            return ValidationResult(
                valid=False,
                normalized_url=None,
                resource_type="website",
                error="URL blocked: hostname resolves to internal IP (SSRF protection)",
            )
    except socket.gaierror:
        pass  # Cannot resolve - allow; will fail at fetch time

    # YouTube format validation
    resource_type = _detect_resource_type(netloc, parsed.path or "")
    if resource_type == "youtube":
        yt_error = _validate_youtube_format(url, parsed)
        if yt_error:
            return ValidationResult(
                valid=False,
                normalized_url=None,
                resource_type="youtube",
                error=yt_error,
            )

    normalized = _normalize_url(url)
    return ValidationResult(
        valid=True,
        normalized_url=normalized,
        resource_type=resource_type,
        error=None,
    )
