from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "regnskap-agent"
DEFAULT_FOLIO_BASE_URL = "https://api.folio.no/v2"


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME / "config.json"


@dataclass
class Config:
    token: str | None = None
    default_company: str | None = None
    folio_token: str | None = None
    folio_base_url: str | None = None


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(
        token=data.get("fiken_api_token"),
        default_company=data.get("default_company"),
        folio_token=data.get("folio_api_token"),
        folio_base_url=data.get("folio_base_url"),
    )


def save_config(config: Config, path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "fiken_api_token": config.token,
        "default_company": config.default_company,
        "folio_api_token": config.folio_token,
        "folio_base_url": config.folio_base_url,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


def resolve_token(config: Config) -> str:
    token = os.environ.get("FIKEN_API_TOKEN") or config.token
    if not token:
        raise RuntimeError(
            "Mangler Fiken-token. Kjør `regnskap setup --token ...` eller sett FIKEN_API_TOKEN."
        )
    return token


def resolve_company(config: Config, company: str | None) -> str:
    resolved = company or os.environ.get("FIKEN_COMPANY") or config.default_company
    if not resolved:
        raise RuntimeError(
            "Mangler company slug. Bruk `--company`, sett FIKEN_COMPANY, eller kjør `regnskap setup --company ...`."
        )
    return resolved


def resolve_folio_token(config: Config) -> str:
    token = os.environ.get("FOLIO_API_TOKEN") or config.folio_token
    if not token:
        raise RuntimeError(
            "Mangler Folio-token. Kjør `regnskap folio setup --token-stdin --base-url ...` "
            "eller sett FOLIO_API_TOKEN."
        )
    return token


def resolve_folio_base_url(config: Config, base_url: str | None = None) -> str:
    return base_url or os.environ.get("FOLIO_API_BASE_URL") or config.folio_base_url or DEFAULT_FOLIO_BASE_URL
