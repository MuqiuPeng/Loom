"""Built-in triggers for Loom workflows.

Import this module to register all built-in triggers.
"""

# Import to trigger registration
from loom.triggers.manual import ManualTrigger

__all__ = ["ManualTrigger"]
