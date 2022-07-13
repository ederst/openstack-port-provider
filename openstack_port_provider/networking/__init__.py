from enum import Enum

from .netplan import NetplanNetworkingConfigHandler


class NetworkingConfigType(str, Enum):
    netplan = "netplan"


def get_networking_config_handler(config_type: NetworkingConfigType, **kwargs):
    if config_type == NetworkingConfigType.netplan:
        if "apply_cmd" in kwargs:
            return NetplanNetworkingConfigHandler(apply_cmd=kwargs['apply_cmd'])
        return NetplanNetworkingConfigHandler()

    raise ValueError(f"No networking config handler for '{config_type.value}' found.")
