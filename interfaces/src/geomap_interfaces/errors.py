"""Stable client errors. Messages stay free of paths, tokens, and file bytes."""


class InterfaceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class RegistryError(InterfaceError):
    def __init__(self, message: str):
        super().__init__("invalid_registry", message, 500)


class WmsError(InterfaceError):
    """OGC ServiceException. ``code`` is the OGC exception code."""

    def __init__(self, ogc_code: str, message: str, status: int = 400):
        super().__init__(ogc_code, message, status)
        self.ogc_code = ogc_code
