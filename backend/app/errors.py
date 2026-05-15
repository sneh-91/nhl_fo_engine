from __future__ import annotations


class ExternalAPIError(RuntimeError):
    """Base error for upstream source failures."""


class MissingConfigurationError(ExternalAPIError):
    """Raised when a required API setting is missing."""


class UpstreamRequestError(ExternalAPIError):
    def __init__(
        self,
        *,
        source: str,
        path: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        self.source = source
        self.path = path
        self.status_code = status_code

        if status_code is None:
            full_message = f"{source} request failed for {path}: {message}"
        else:
            full_message = f"{source} request failed for {path}: {status_code} {message}"

        super().__init__(full_message)
