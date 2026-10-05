import pytest
from pydantic import ValidationError

from app.api.schemas import MonitorCreate, ProjectCreate
from app.config import Settings
from app.domain.monitors import cycle_budget_ms, validate_check_config, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "https://user:password@example.com",
        "https://example.com/#x",
        "https://example.com/#",
        "https://example.com:8080",
        "https://example.com:",
        "http://localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://169.254.169.254",
        "http://224.0.0.1",
        "http://[ff02::1]",
        "http://[::1]",
        "http://[::ffff:8.8.8.8]",
        "http://[fe80::1%25eth0]",
        "http://2130706433",
        "http://0x7f000001",
        "http://127.1",
        "http://app.internal",
        "http://example.com\\@evil.test",
        "http://example.com\n",
        "https://example.com/?api_key=x",
        "https://example.com/?access_token=x",
        "https://example.com/?%74oken=x",
        "https://example.com/" + "x" * 2048,
    ],
)
def test_rn003_rejects_unsafe_or_invalid_urls_without_network(url):
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("HTTPS://EXAMPLE.COM", "https://example.com/"),
        ("https://example.com:443/health?region=br", "https://example.com:443/health?region=br"),
        ("http://8.8.8.8:80/", "http://8.8.8.8:80/"),
        ("https://[2606:4700:4700::1111]/", "https://[2606:4700:4700::1111]/"),
    ],
)
def test_rn003_normalization(url, expected):
    assert validate_url(url) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("method", "POST"),
        ("interval_seconds", 59),
        ("interval_seconds", 3601),
        ("timeout_ms", 999),
        ("timeout_ms", 15001),
        ("expected_status", 199),
        ("expected_status", 600),
        ("failure_threshold", 0),
        ("failure_threshold", 11),
        ("retry_count", -1),
        ("retry_count", 3),
        ("latency_threshold_ms", 99),
        ("latency_threshold_ms", 15001),
        ("latency_threshold_ms", 5001),
        ("retry_count", True),
        ("timeout_ms", "5000"),
        ("name", "   "),
    ],
)
def test_rn004_and_rn005_limits(field, value):
    with pytest.raises(ValidationError):
        MonitorCreate.model_validate(
            {"name": "health", "url": "https://example.com/", field: value}
        )


def test_rn006_budget_includes_maximum_jitter_and_overhead():
    assert cycle_budget_ms(15000, 2) == 49800
    assert cycle_budget_ms(5000, 1) == 13600
    validate_check_config(
        {
            "latency_threshold_ms": None,
            "timeout_ms": 15000,
            "retry_count": 2,
            "interval_seconds": 60,
        }
    )
    for timeout, interval in [(16000, 60), (15000, 49)]:
        with pytest.raises(ValueError):
            validate_check_config(
                {
                    "latency_threshold_ms": None,
                    "timeout_ms": timeout,
                    "retry_count": 2,
                    "interval_seconds": interval,
                }
            )


def test_client_cannot_assign_ownership_or_lifecycle():
    with pytest.raises(ValidationError):
        ProjectCreate(name="project", owner_id="someone")
    with pytest.raises(ValidationError):
        MonitorCreate(name="monitor", url="https://example.com", health_status="online")


def test_production_config_rejects_insecure_origins_and_defaults():
    with pytest.raises(ValidationError):
        Settings(environment="prod")
    with pytest.raises(ValidationError):
        Settings(
            environment="prod",
            database_url="postgresql+asyncpg://user:pass@db/vigil",
            allowed_origins=["http://app.test"],
        )
    for origin in ["https://app.test/", "https://*.test", "https://user:pass@app.test", "null"]:
        with pytest.raises(ValidationError):
            Settings(allowed_origins=[origin])
    valid = Settings(
        environment="prod",
        database_url="postgresql+asyncpg://user:pass@db/vigil",
        allowed_origins=["https://app.test"],
    )
    assert valid.cookie_secure and valid.cookie_name == "__Host-vigil_session"


@pytest.mark.parametrize(
    "origin",
    [
        "https://app.test:abc",
        "https://app.test:65536",
        "https://app.test:0",
        "https://app.test:",
        "http://[::1]:abc",
        "http://[::1]:65536",
        "http://[::1]:0",
        "http://[::1]:",
        "http://[::1]suffix:80",
    ],
)
def test_origin_rejects_invalid_port_or_authority(origin):
    with pytest.raises(ValidationError, match="exact HTTP"):
        Settings(allowed_origins=[origin], _env_file=None)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
        "http://[::1]",
        "https://app.test:1",
        "https://[2001:db8::1]:65535",
        "https://App.Test:443",
        "https://app.test",
    ],
)
def test_origin_valid_ports_local_ipv6_and_spelling_are_preserved(origin):
    settings = Settings(allowed_origins=[origin], _env_file=None)
    assert settings.allowed_origins == [origin]
