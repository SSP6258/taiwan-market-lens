"""Refresh stale Python modules after a running deployment gains new arguments."""
import importlib
import inspect


def load_renderer(module_name, function_name, required_parameter):
    module = importlib.import_module(module_name)
    function = getattr(module, function_name, None)
    # A stale deployment may lack the function entirely, not just the new parameter.
    if function is None or required_parameter not in inspect.signature(function).parameters:
        importlib.invalidate_caches()
        module = importlib.reload(module)
        function = getattr(module, function_name)
    return function
