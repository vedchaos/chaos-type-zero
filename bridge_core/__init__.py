"""
CHAOS TYPE ZERO bridge_core — Core modules
Features resilient lazy-loading (PEP 562) so optional dependencies (numpy, torch, etc.)
do not prevent core functionality from loading.
"""

import importlib
import logging

logger = logging.getLogger("bridge_core")

_MODULE_EXPORTS = {
    "get_brain": ("smart_brain", "get_brain"),
    "get_memory": ("memory_3tier", "get_memory"),
    "get_orchestrator": ("agents", "get_orchestrator"),
    "classify_task": ("task_classifier", "classify_task"),
    "get_task_chain": ("task_classifier", "get_task_chain"),
    "parse_hinglish_time": ("scheduler", "parse_hinglish_time"),
    "ChaosScheduler": ("scheduler", "ChaosScheduler"),
    "recon_passive": ("recon", "recon_passive"),
    "recon_active": ("recon", "recon_active"),
    "get_voice": ("voice", "get_voice"),
    "get_vision": ("vision", "get_vision"),
    "get_ml_pipeline": ("ml_pipeline", "get_ml_pipeline"),
    "get_engine": ("automation", "get_engine"),
    "get_bridge": ("context_bridge", "get_bridge"),
    "get_cache": ("cache", "get_cache"),
    "get_healer": ("memory_healer", "get_healer"),
    "get_vault": ("vault", "get_vault"),
    "get_heuristics": ("heuristics", "get_heuristics"),
    "get_meta_reasoner": ("meta_reasoner", "get_meta_reasoner"),
    "get_neural": ("neural", "get_neural"),
    "get_voice_enhanced": ("voice_enhanced", "get_voice_enhanced"),
    "get_provenance": ("receipts", "get_provenance"),
}

__all__ = list(_MODULE_EXPORTS.keys())


def __getattr__(name: str):
    """Lazy load core functions on demand to shield against missing optional dependencies."""
    if name in _MODULE_EXPORTS:
        mod_name, func_name = _MODULE_EXPORTS[name]
        try:
            mod = importlib.import_module(f".{mod_name}", package=__name__)
            func = getattr(mod, func_name)
            globals()[name] = func
            return func
        except ImportError as exc:
            err_msg = str(exc)
            logger.warning(f"Optional module {mod_name} could not be loaded: {err_msg}")
            def _stub(*args, **kwargs):
                raise RuntimeError(
                    f"'{name}' is unavailable because optional dependency for '{mod_name}' is missing: {err_msg}"
                )
            globals()[name] = _stub
            return _stub
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    return __all__
