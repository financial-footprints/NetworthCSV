"""Library exceptions for NetworthCSV."""


class NetworthCsvError(Exception):
    """Base error for NetworthCSV library callers."""


class ConfigError(NetworthCsvError):
    """Invalid or missing configuration."""


class PipelineError(NetworthCsvError):
    """Pipeline stage failure."""


class StageError(PipelineError):
    """Operational failure inside a pipeline stage."""
