"""Failures the API reports by code. See the error table in the API contract."""


class HarnessError(Exception):
    """A refusal with a code a client renders."""

    code = "internal"
    status = 500

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


def _error(name, code, status):
    return type(name, (HarnessError,), {"code": code, "status": status})


InvalidArgs = _error("InvalidArgs", "invalid_args", 400)
UnknownOperation = _error("UnknownOperation", "unknown_operation", 400)
NotAllowedForActor = _error("NotAllowedForActor", "not_allowed_for_actor", 403)
NotFound = _error("NotFound", "not_found", 404)
StaleVersion = _error("StaleVersion", "stale_version", 409)
GateAlreadyAnswered = _error("GateAlreadyAnswered", "gate_already_answered", 409)
IllegalTransition = _error("IllegalTransition", "illegal_transition", 409)
ConfirmationInvalid = _error("ConfirmationInvalid", "confirmation_invalid", 409)
CritiqueErrors = _error("CritiqueErrors", "critique_errors", 422)
RunExternallyHeld = _error("RunExternallyHeld", "run_externally_held", 423)
