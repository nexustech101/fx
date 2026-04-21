"""
fx: project structuring and management tooling built on the
registers CLI + DB framework.
"""

from fx.commands import fx_VERSION, get_registry, main, run

__version__ = fx_VERSION

__all__ = ["run", "main", "get_registry", "__version__"]
