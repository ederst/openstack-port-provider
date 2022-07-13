from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Any


class BaseNetworkingConfigHandler(metaclass=ABCMeta):
    @abstractmethod
    def create(
        self,
        os_ports: Any,
        os_subnets: Any,
        config_destination: Path,
        config_templates: Path,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def apply(self) -> None:
        raise NotImplementedError
