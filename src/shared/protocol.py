"""Framework-independent wire data for the Phase 1 health endpoint."""

from dataclasses import dataclass
from typing import Literal

SERVICE_NAME = "contexttrace-backend"
API_VERSION = 1
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class HealthStatus:
    version: str
    service: str = SERVICE_NAME
    status: Literal["running"] = "running"
    api_version: int = API_VERSION


@dataclass(frozen=True)
class HealthResponse:
    data: HealthStatus
    ok: Literal[True] = True
    error: None = None


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str


@dataclass(frozen=True)
class ErrorResponse:
    error: ApiError
    ok: Literal[False] = False
    data: None = None
