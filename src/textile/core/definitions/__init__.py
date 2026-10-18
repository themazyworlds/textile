"""
Textile Definitions Functional Domain Package.
Provides Intent DAG nodes, layer priority definitions,
error hierarchy, and system feature detection.
"""

from textile.core.definitions.errors import (
    STRAND_EXEC_ERRORS,
    OTPChallengeRequiredError,
    PolicyViolationError,
    SandboxUnavailableError,
    TextileError,
)
lazy from textile.core.definitions.settings import (
    YarnSettings,
    dumps_toml,
    generate_documented_toml,
    get_settings_file_path,
    get_user_yarn_settings,
)

__all__ = [
    "OTPChallengeRequiredError",
    "PolicyViolationError",
    "STRAND_EXEC_ERRORS",
    "SandboxUnavailableError",
    "TextileError",
    "YarnSettings",
    "dumps_toml",
    "generate_documented_toml",
    "get_settings_file_path",
    "get_user_yarn_settings",
]
