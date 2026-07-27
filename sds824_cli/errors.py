class Sds824Error(Exception):
    """Base error shown by the CLI."""


class TransportError(Sds824Error):
    """Raised when USBTMC communication fails."""


class ProtocolError(Sds824Error):
    """Raised when a command or response is invalid."""
