from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "regnskap-agent"
DEFAULT_FOLIO_BASE_URL = "https://api.folio.no/v2"
DEFAULT_TRIPLETEX_BASE_URL = "https://tripletex.no/v2"
DEFAULT_UNIMICRO_API_BASE_URL = "https://api.unimicro.no"
DEFAULT_UNIMICRO_FILE_BASE_URL = "https://files.unimicro.no"


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
    tripletex_consumer_token: str | None = None
    tripletex_employee_token: str | None = None
    tripletex_company_id: str | None = None
    tripletex_base_url: str | None = None
    tripletex_session_token: str | None = None
    tripletex_session_expires: str | None = None
    unimicro_api_token: str | None = None
    unimicro_company_key: str | None = None
    unimicro_api_base_url: str | None = None
    unimicro_file_base_url: str | None = None


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
        tripletex_consumer_token=data.get("tripletex_consumer_token"),
        tripletex_employee_token=data.get("tripletex_employee_token"),
        tripletex_company_id=data.get("tripletex_company_id"),
        tripletex_base_url=data.get("tripletex_base_url"),
        tripletex_session_token=data.get("tripletex_session_token"),
        tripletex_session_expires=data.get("tripletex_session_expires"),
        unimicro_api_token=data.get("unimicro_api_token"),
        unimicro_company_key=data.get("unimicro_company_key"),
        unimicro_api_base_url=data.get("unimicro_api_base_url"),
        unimicro_file_base_url=data.get("unimicro_file_base_url"),
    )


def save_config(config: Config, path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "fiken_api_token": config.token,
        "default_company": config.default_company,
        "folio_api_token": config.folio_token,
        "folio_base_url": config.folio_base_url,
        "tripletex_consumer_token": config.tripletex_consumer_token,
        "tripletex_employee_token": config.tripletex_employee_token,
        "tripletex_company_id": config.tripletex_company_id,
        "tripletex_base_url": config.tripletex_base_url,
        "tripletex_session_token": config.tripletex_session_token,
        "tripletex_session_expires": config.tripletex_session_expires,
        "unimicro_api_token": config.unimicro_api_token,
        "unimicro_company_key": config.unimicro_company_key,
        "unimicro_api_base_url": config.unimicro_api_base_url,
        "unimicro_file_base_url": config.unimicro_file_base_url,
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


def resolve_tripletex_consumer_token(config: Config) -> str:
    token = os.environ.get("TRIPLETEX_CONSUMER_TOKEN") or config.tripletex_consumer_token
    if not token:
        raise RuntimeError(
            "Mangler Tripletex consumer token. Kjør `regnskap tripletex setup --consumer-token-stdin "
            "--employee-token-stdin` eller sett TRIPLETEX_CONSUMER_TOKEN."
        )
    return token


def resolve_tripletex_employee_token(config: Config) -> str:
    token = os.environ.get("TRIPLETEX_EMPLOYEE_TOKEN") or config.tripletex_employee_token
    if not token:
        raise RuntimeError(
            "Mangler Tripletex employee token. Kjør `regnskap tripletex setup --consumer-token-stdin "
            "--employee-token-stdin` eller sett TRIPLETEX_EMPLOYEE_TOKEN."
        )
    return token


def resolve_tripletex_company_id(config: Config, company_id: str | None = None) -> str:
    return company_id or os.environ.get("TRIPLETEX_COMPANY_ID") or config.tripletex_company_id or "0"


def resolve_tripletex_base_url(config: Config, base_url: str | None = None) -> str:
    return base_url or os.environ.get("TRIPLETEX_BASE_URL") or config.tripletex_base_url or DEFAULT_TRIPLETEX_BASE_URL


def resolve_unimicro_api_token(config: Config) -> str:
    token = os.environ.get("UNIMICRO_API_TOKEN") or config.unimicro_api_token
    if not token:
        raise RuntimeError(
            "Mangler UniMicro API-token. Kjør `regnskap unimicro setup --token-stdin "
            "--company-key ...` eller sett UNIMICRO_API_TOKEN."
        )
    return token


def resolve_unimicro_company_key(config: Config, company_key: str | None = None) -> str:
    resolved = company_key or os.environ.get("UNIMICRO_COMPANY_KEY") or config.unimicro_company_key
    if not resolved:
        raise RuntimeError(
            "Mangler UniMicro company key. Bruk `--company-key`, sett UNIMICRO_COMPANY_KEY, "
            "eller kjør `regnskap unimicro setup --company-key ...`."
        )
    return resolved


def resolve_unimicro_api_base_url(config: Config, base_url: str | None = None) -> str:
    return base_url or os.environ.get("UNIMICRO_API_BASE_URL") or config.unimicro_api_base_url or DEFAULT_UNIMICRO_API_BASE_URL


def resolve_unimicro_file_base_url(config: Config, base_url: str | None = None) -> str:
    return (
        base_url
        or os.environ.get("UNIMICRO_FILE_BASE_URL")
        or config.unimicro_file_base_url
        or DEFAULT_UNIMICRO_FILE_BASE_URL
    )
