from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Any


class BaseNetworkingConfigHandler(metaclass=ABCMeta):
    def __init__(self, should_apply: bool = True) -> None:
        self.should_apply = should_apply

    @abstractmethod
    def create(
        self,
        os_port: Any,
        os_subnet: Any,
        config_destination: Path,
        config_templates: Path,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def apply(self) -> None:
        raise NotImplementedError

    @property
    def should_apply(self) -> bool:
        return self._should_apply

    @should_apply.setter
    def should_apply(self, value: bool):
        self._should_apply = value
