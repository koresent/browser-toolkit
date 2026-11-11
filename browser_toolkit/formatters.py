import json
import os
from typing import Any, Callable, Optional

try:
    import toon_format
except ImportError:
    toon_format = None


def resolve_format(args: Any) -> str:
    """Resolves output format ('text', 'toon', 'json', 'json-pretty')."""
    if getattr(args, "toon", False):
        return "toon"
    if getattr(args, "json", False):
        return "json"
    explicit_fmt = getattr(args, "format", None)
    if explicit_fmt and explicit_fmt.lower() in ("toon", "json", "json-pretty", "text"):
        return explicit_fmt.lower()
    env_fmt = os.getenv("BROWSER_TOOLKIT_FORMAT", "").strip().lower()
    if env_fmt in ("toon", "json", "json-pretty"):
        return env_fmt
    return "text"


def dump_data(data: Any, fmt: str = "toon", compact: bool = True) -> str:
    """Serializes data into requested format (toon, json, json-pretty)."""
    if fmt == "toon":
        if toon_format is not None:
            return toon_format.dumps(data)
        return json.dumps(data, separators=(",", ":"))
    if fmt == "json":
        return json.dumps(data, separators=(",", ":") if compact else None, indent=None if compact else 2)
    if fmt == "json-pretty":
        return json.dumps(data, indent=2)
    return str(data)


def to_toon(data: Any, compact: bool = True) -> str:
    """Serializes data into TOON format."""
    return dump_data(data, fmt="toon", compact=compact)


def output_result(
    data: Any,
    args: Any,
    text_printer: Optional[Callable[[Any], None]] = None,
) -> None:
    """Outputs data according to resolved format or delegates to text printer."""
    fmt = resolve_format(args)
    if fmt in ("toon", "json", "json-pretty"):
        print(dump_data(data, fmt=fmt))
    elif text_printer:
        text_printer(data)
