import logging
import subprocess
from pathlib import Path
from typing import Any, List

import yaml

from ..base import BaseNetworkingConfigHandler

NAME_PREFIX = "opp"
INTERFACE_NUMBER_OFFSET = 4


class NetplanNetworkingConfigHandler(BaseNetworkingConfigHandler):
    def __init__(self, apply_cmd: List[str] = ['netplan', 'apply']) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.apply_cmd = apply_cmd
        # Note(sprietl): Assume (for simplicity) that on startup the network config has to be applied.
        self.should_apply = True

    def create(
        self,
        os_ports: Any,
        os_subnets: Any,
        config_destination: Path,
        config_templates: Path,
    ) -> None:
        # Note(sprietl):
        #   This is a naive approach on how to number the interfaces.
        #   But for complexity reasons we leave it for now like this.
        if_number = INTERFACE_NUMBER_OFFSET

        for os_port in os_ports:
            if len(os_port.fixed_ips) > 1:
                self.logger.warning(f"Port '{os_port.name}' has more than one IP address ({os_port.fixed_ips}).")

            # Note(sprietl): For now we only get the first fixed IP
            os_port_fixed_ip = os_port.fixed_ips[0]
            os_port_subnet_id = os_port_fixed_ip['subnet_id']

            # ignore ports with subnets not in expected subnets
            if os_port_subnet_id not in os_subnets:
                self.logger.debug(
                    msg=(
                        f"Ignore port '{os_port.name}'"
                        f"because subnet with ID '{os_port_subnet_id}' does not match any of the provided subnets."
                    )
                )
                continue

            os_subnet = os_subnets[os_port_subnet_id]

            networking_if_name = f"ens{if_number}"
            config_base_name = f"51-{NAME_PREFIX}-{networking_if_name}.yaml"
            config_path = config_destination / config_base_name

            if not config_path.is_file():
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
