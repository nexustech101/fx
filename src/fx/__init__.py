"""
FX: project structuring and management tooling built on the
registers CLI + DB framework.
"""

from fx.commands import FX_VERSION, get_registry, main, run

__version__ = FX_VERSION

__all__ = ["run", "main", "get_registry", "__version__"]
