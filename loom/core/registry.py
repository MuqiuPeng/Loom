"""Step registry - maps step names to implementation classes."""

from typing import Type

from loom.core.step import Step


class StepRegistry:
    """Registry for Step implementations.

    Allows WorkflowRunner to find Step classes by name string.

    Usage:
        # Register a step
        registry.register("parse-jd", ParseJDStep)

        # Get a step instance
        step = registry.get("parse-jd")
    """

    _instance: "StepRegistry | None" = None
    _steps: dict[str, Type[Step]]

    def __new__(cls) -> "StepRegistry":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._steps = {}
        return cls._instance

    def register(self, name: str, step_class: Type[Step]) -> None:
        """Register a step class with a name.

        Args:
            name: Step name, e.g. "parse-jd"
            step_class: The Step implementation class
        """
        self._steps[name] = step_class

    def get(self, name: str) -> Step:
        """Get a step instance by name.

        Args:
            name: Step name

        Returns:
            Instantiated Step

        Raises:
            KeyError: If step name is not registered
        """
        if name not in self._steps:
            raise KeyError(f"Step '{name}' not registered")
        return self._steps[name]()

    def list_steps(self) -> list[str]:
        """List all registered step names."""
        return list(self._steps.keys())


# Global registry instance
step_registry = StepRegistry()
