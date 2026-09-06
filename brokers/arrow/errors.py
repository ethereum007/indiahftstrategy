class ArrowError(Exception):
    """Base Arrow integration error."""


class ArrowConfigurationError(ArrowError):
    pass


class ArrowAuthenticationError(ArrowError):
    pass


class ArrowProtocolError(ArrowError):
    pass


class ArrowRateLimitError(ArrowError):
    pass


class ArrowInstrumentError(ArrowError):
    pass


class ArrowExternalValidationRequired(ArrowError):
    pass
