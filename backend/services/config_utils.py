"""Fail-safe config value parsers.

Prevents ValueError from unsafe bool/int parsing of SQLite TEXT fields,
JSON values, or environment variables. Used by network_beacon, network_sync,
ollama_proxy, recon_train, train_presets.
"""


def safe_bool(value: object, default: bool = False) -> bool:
    """Parse bool from any source (SQLite TEXT, JSON, env var).

    Accepts: True/False, 1/0, 'true'/'false', '1'/'0', 'yes'/'no', None.
    Returns default on any unparseable value.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ('1', 'true', 'yes', 'on', 'y', 't'):
        return True
    if s in ('0', 'false', 'no', 'off', 'n', 'f', ''):
        return False
    return default


def safe_int(value: object, default: int = 0) -> int:
    """Parse int from any source. Returns default on failure."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default
