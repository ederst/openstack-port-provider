import logging
import subprocess
from pathlib import Path
from typing import Any, List

import psutil
import yaml

from ..base import BaseNetworkingConfigHandler

NAME_PREFIX = "opp"
INTERFACE_NUMBER_OFFSET = 4


class NetplanNetworkingConfigHandler(BaseNetworkingConfigHandler):
    def __init__(self, apply_cmd: List[str] = ['netplan', 'apply']) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.apply_cmd = apply_cmd

    def create(
        self,
        os_port: Any,
        os_subnet: Any,
        config_destination: Path,
        config_templates: Path,
    ) -> None:
        # Note(sprietl):
        #   This is a naive approach on how to number the interfaces.
        #   But for complexity reasons we leave it for now like this.
        # TODO(sprietl):
        #   This is a bug, when adding multiple interfaces name stays the same.
        #   Move to loop, and make sure if is unique.
        if_number = INTERFACE_NUMBER_OFFSET
        networking_if_name = f"ens{if_number}"

        net_if_stats = psutil.net_if_stats()
        # TODO(sprietl):
        #   * Test if if is up as well (net_if_stats[networking_if_name].isup)?
        #   * Make configurable if this should lead to abort, or error, for now just ignore and warn.
        if networking_if_name in net_if_stats:
            self.logger.warning(
                f"Interface with name {networking_if_name} already exists, not creating/applying network config."
            )
            self.should_apply = False
            return

        if len(os_port.fixed_ips) > 1:
            self.logger.warning(f"Port '{os_port.name}' has more than one IP address ({os_port.fixed_ips}).")

        # Note(sprietl): For now we only get the first fixed IP
        os_port_fixed_ip = os_port.fixed_ips[0]
        os_port_subnet_id = os_port_fixed_ip['subnet_id']

        if os_port_subnet_id != os_subnet.id:
            raise ValueError(f"Provided port '{os_port.name}' is not in provided subnet '{os_subnet.name}'")

        config_base_name = f"51-{NAME_PREFIX}-{networking_if_name}.yaml"
        config_path = config_destination / config_base_name

        config_template_base_name = f"{os_subnet.name}.yaml"
        config_templates_path = config_templates / config_template_base_name

        with open(config_templates_path, "r") as f:
            networking_config = yaml.safe_load(f)

        networking_if_address = f"{os_port_fixed_ip['ip_address']}/{os_subnet.cidr.split('/')[-1]}"

        networking_if_config = networking_config['network']['ethernets'].pop("ensX")
        networking_if_config['addresses'] = [networking_if_address]
        networking_if_config['match']['macaddress'] = os_port['mac_address']
        networking_if_config['set-name'] = networking_if_name
        networking_config['network']['ethernets'][networking_if_name] = networking_if_config

        with open(config_path, "w") as f:
            networking_config_yaml = yaml.safe_dump(networking_config)
            self.logger.debug(networking_config_yaml)
            f.write(networking_config_yaml)

        self.should_apply = True

    def _format_output(self, output: bytes, indent: int = 4) -> str:
        lines = output.decode().strip("\n").splitlines()

        formatted_output = ""
        for line in lines:
            formatted_output += f"{' ' * indent}{line}\n"

        return formatted_output

    def apply(self) -> None:
        if not self.should_apply:
            self.logger.debug("Nothing to apply.")
            return

        self.logger.info("Apply networking config.")
        try:
            netplan_output = self._format_output(subprocess.check_output(self.apply_cmd, stderr=subprocess.STDOUT))
            self.logger.debug(f"Netplan output:\n{netplan_output}")
            self.should_apply = False
        except subprocess.CalledProcessError as e:
            netplan_output = self._format_output(e.output)
            self.logger.error(f"Unable to apply networking config: {e}\n  Netplan output:\n{netplan_output}")
            raise e
