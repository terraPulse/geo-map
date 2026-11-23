"""API errors. Messages are safe to return to an authenticated caller."""


class LayerManagerError(Exception):
    code = "error"
    status = 400

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or []

    def to_body(self):
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


class Unauthorized(LayerManagerError):
    code = "unauthorized"
    status = 401


class Forbidden(LayerManagerError):
    code = "forbidden"
    status = 403


class NotFound(LayerManagerError):
    code = "not_found"
    status = 404


class Conflict(LayerManagerError):
    code = "conflict"
    status = 409


class ConfirmationRequired(LayerManagerError):
    code = "confirmation_required"
    status = 409


class ValidationFailed(LayerManagerError):
    code = "validation_failed"
    status = 422


class PayloadTooLarge(LayerManagerError):
    code = "payload_too_large"
    status = 413


class ConfigurationError(LayerManagerError):
    code = "configuration_error"
    status = 500
