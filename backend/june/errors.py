class JuneError(Exception):
    """A safe, actionable message that can be returned to June's interface."""
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
