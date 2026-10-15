#!/usr/bin/env python3
"""
Master Test Runner for Textile Application.
Runs Unit, Integration, and E2E test suites in sequence.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_all():
    sys.exit(pytest.main([str(PROJECT_ROOT / "tests"), *sys.argv[1:]]))


if __name__ == "__main__":
    run_all()
