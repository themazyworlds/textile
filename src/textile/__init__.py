"""
Textile • Modular AI Subsystem & Desktop Intelligence Engine.
"""

import warnings

# Suppress upstream library deprecation warnings from typing internals on Python 3.14+
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*_UnionGenericAlias.*")

__version__ = "0.1.0"
