import ipaddress
import re
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

CHECK_FIELDS = frozenset(
    {
        "url",
        "method",
        "interval_seconds",
        "timeout_ms",
        "expected_status",
        "failure_threshold",
        "retry_count",
        "latency_threshold_ms",
    }
)
SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "key",
    "signature",
    "credential",
}


def validate_url(value: str) -> str:
    # Validation never resolves DNS or performs HTTP. Connection-time SSRF is future work.
    if len(value) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("URL must be at most 2048 characters without whitespace or controls")
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise ValueError("Invalid URL") from None
    if parts.scheme not in {"http", "https"} or not host or not parts.netloc:
        raise ValueError("URL must use HTTP or HTTPS with a hostname")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValueError("URL credentials are forbidden")
    if "#" in value or port not in {None, 80, 443} or parts.netloc.endswith(":"):
        raise ValueError("URL fragments and ports other than 80/443 are forbidden")
    if "%" in host or host.lower().rstrip(".") in {"localhost", "localhost.localdomain"}:
        raise ValueError("URL hostname is forbidden")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", host) or host.lower().startswith("0x"):
            raise ValueError("Ambiguous IP address") from None
        try:
            ascii_host = host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("Invalid hostname") from None
        labels = ascii_host.rstrip(".").split(".")
        if len(labels) < 2 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
        ):
            raise ValueError("Invalid public hostname")
        if ascii_host.rstrip(".").endswith((".localhost", ".local", ".internal")):
            raise ValueError("Private hostname")
        netloc = ascii_host
    else:
        if (
            not address.is_global
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or address.is_loopback
            or address.is_link_local
        ) or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None):
            raise ValueError("Only public IP addresses are permitted")
        netloc = f"[{address.compressed}]" if address.version == 6 else address.compressed
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        normalized = unquote(key).lower().replace("-", "_")
        if normalized in SECRET_KEYS or any(normalized.endswith("_" + s) for s in SECRET_KEYS):
            raise ValueError("Secrets in URL query parameters are forbidden")
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def cycle_budget_ms(timeout_ms: int, retry_count: int) -> int:
    # Maximum jitter: +20% for each 500ms/1000ms backoff, plus 3s overhead.
    return (retry_count + 1) * timeout_ms + sum((600, 1200)[:retry_count]) + 3000


def validate_check_config(config: dict) -> None:
    threshold = config["latency_threshold_ms"]
    if threshold is not None and threshold > config["timeout_ms"]:
        raise ValueError("latency_threshold_ms must be <= timeout_ms")
    budget = cycle_budget_ms(config["timeout_ms"], config["retry_count"])
    if budget > 50000 or budget >= config["interval_seconds"] * 1000:
        raise ValueError("Cycle budget must be <= 50000ms and less than interval")
