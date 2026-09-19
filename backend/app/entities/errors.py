class InvalidSessionToken(Exception):
    """The session token is missing, malformed, tampered with or expired."""


class SessionMessageLimitExceeded(Exception):
    """The session has used up its message allowance."""


class HumanCheckFailed(Exception):
    """The human-verification (CAPTCHA) token was rejected."""
