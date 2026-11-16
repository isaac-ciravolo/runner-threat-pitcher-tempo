"""Validation and provenance helpers that remain active under ``python -O``."""
import hashlib
import platform
from importlib.metadata import version
from pathlib import Path


class ValidationError(ValueError):
    """An input or artifact violates a research pipeline requirement."""


def require(condition, message):
    if not condition:
        raise ValidationError(str(message))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_hash(path, expected):
    observed = sha256_file(path)
    require(observed == expected, f'Input checksum mismatch: {path}')
    return observed


def current_environment():
    return {
        'python': platform.python_version(),
        'pandas': version('pandas'),
        'numpy': version('numpy'),
        'sklearn': version('scikit-learn'),
    }
