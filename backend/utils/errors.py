"""Expected business failures. Messages are plain Arabic for the user.

Services raise these; the API layer turns them into HTTP responses.
"""


class DomainError(Exception):
    """A rule was broken, e.g. an unbalanced entry or a locked period (HTTP 400)."""

    status_code = 400

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class Conflict(DomainError):
    """The record changed under the user, e.g. a request already decided (HTTP 409)."""

    status_code = 409


def need(condition: object, message: str, field: str | None = None) -> None:
    if not condition:
        raise DomainError(message, field)
