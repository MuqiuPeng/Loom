"""Trigger registry - maps trigger names to implementation classes."""

from typing import Type

from loom.core.trigger import Trigger


class TriggerRegistry:
    """Registry for Trigger implementations.

    Allows WorkflowRunner to find Trigger classes by name string.

    Usage:
        # Register a trigger
        trigger_registry.register("manual", ManualTrigger)

        # Get a trigger instance
        trigger = trigger_registry.get("manual")
    """

    _instance: "TriggerRegistry | None" = None
    _triggers: dict[str, Type[Trigger]]

    def __new__(cls) -> "TriggerRegistry":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._triggers = {}
        return cls._instance

    def register(self, name: str, trigger_class: Type[Trigger]) -> None:
        """Register a trigger class with a name.

        Args:
            name: Trigger name, e.g. "manual"
            trigger_class: The Trigger implementation class
        """
        self._triggers[name] = trigger_class

    def get(self, name: str) -> Trigger:
        """Get a trigger instance by name.

        Args:
            name: Trigger name

        Returns:
            Instantiated Trigger

        Raises:
            KeyError: If trigger name is not registered
        """
        if name not in self._triggers:
            raise KeyError(f"Trigger '{name}' not registered")
        return self._triggers[name]()

    def list_triggers(self) -> list[str]:
        """List all registered trigger names."""
        return list(self._triggers.keys())


# Global registry instance
trigger_registry = TriggerRegistry()
