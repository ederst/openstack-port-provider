import configparser
import logging
import time
from enum import Enum
from pathlib import Path
from typing import List

import openstack.connection as openstack_connection
import typer

from ..networking import NetworkingConfigType, get_networking_config_handler

app = typer.Typer()

PORT_NAME_PREFIX = "opp"
NODE_NAME_ENV_VAR = "NODENAME"

LOG_FORMAT = "%(asctime)s.%(msecs)-3d %(levelname)-8s [%(filename)s:%(lineno)-3d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LogLevel(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class TyperLoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        typer.echo(self.format(record))


def _cloud_config_option() -> typer.Option:
    return typer.Option(
        default="/etc/kubernetes/cloud.config",
        help="Path to the cloud config of the OpenStack CCM",
        exists=True,
        file_okay=True,
        dir_okay=False,
        writable=False,
        readable=True,
        resolve_path=True,
    )


def _subnets_option() -> typer.Option:
    return typer.Option(..., "--subnet", help="Subnet to add ports from")


def _node_name_option() -> typer.Option:
    return typer.Option(..., envvar=NODE_NAME_ENV_VAR)


def _log_level_option() -> typer.Option:
    return typer.Option(default=LogLevel.INFO)


def _networking_config_templates_option() -> typer.Option:
    return typer.Option(
        default="/etc/os-port-provider/config-templates",
        help="Path to networking config templates",
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=False,
        readable=True,
        resolve_path=True,
    )


def _networking_config_type_option() -> typer.Option:
    return typer.Option(default=NetworkingConfigType.netplan)


def _networking_config_destination_option() -> typer.Option:
    return typer.Option(
        default="/etc/netplan",
        help="Path to networking config destination",
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=True,
    )


def _reconciliation_interval_option() -> typer.Option:
    return typer.Option(default=30, help="Reconciliation intervall in seconds", min=0)


@app.command()
def main(
    cloud_config: Path = _cloud_config_option(),
    node_name: str = _node_name_option(),
    subnets: List[str] = _subnets_option(),
    networking_config_type: NetworkingConfigType = _networking_config_type_option(),
    networking_config_destination: Path = _networking_config_destination_option(),
    networking_config_templates: Path = _networking_config_templates_option(),
    reconciliation_interval: int = _reconciliation_interval_option(),
    apply_cmd: str = typer.Option(default=None, help="Specify a custom apply cmd"),
    log_level: LogLevel = _log_level_option(),
):
    # setup logging
    logging.basicConfig(
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        level=log_level.value,
        handlers=[TyperLoggingHandler()],
    )
    logger = logging.getLogger(__name__)

    # setup OS connection
    cloud_config_parser = configparser.ConfigParser()
    cloud_config_parser.read(cloud_config)

    os_options = {k: v.strip('"') for k, v in cloud_config_parser['global'].items() if v.strip('"')}
    if "application-credential-id" in os_options:
        os_options['auth-type'] = "v3applicationcredential"

    os_conn = openstack_connection.from_config(**os_options)

    # get node
    os_server = os_conn.get_server(node_name)

    if not os_server:
        logger.critical(f"Unable to find server '{node_name}'.")
        raise typer.Exit(1)

    # get subnets
    os_expected_subnets = {}
    for subnet in subnets:
        os_subnet = os_conn.get_subnet(subnet)

        if not os_subnet:
            logger.critical(f"Unable to find subnet '{subnet}'.")

        os_expected_subnets[os_subnet.id] = os_subnet

    # setup networking config handler
    networking_config_handler_kwargs = {}
    if apply_cmd:
        apply_cmd = apply_cmd.split()
        logger.debug(f"Set apply cmd to: {apply_cmd}")
        networking_config_handler_kwargs['apply_cmd'] = apply_cmd

    networking_config_handler = get_networking_config_handler(
        networking_config_type, **networking_config_handler_kwargs
    )

    # main loop
    while True:
        # get actual subnet ids from the ports attached to the server
        os_actual_ports = os_conn.list_ports(filters={'device_id': os_server.id})
        os_actual_subnet_ids = []
        for os_port in os_actual_ports:
            for fixed_ip in os_port.fixed_ips:
                os_actual_subnet_ids.append(fixed_ip['subnet_id'])

        # find out what subnets are missing on the server
        os_expected_subnet_ids = set(os_expected_subnets.keys())
        os_missing_subnet_ids = set(os_expected_subnet_ids) - set(os_actual_subnet_ids)

        logger.debug(
            msg=(
                "Result of missing subnets calculation:\n"
                f"  actual:   {os_actual_subnet_ids}\n"
                f"  expected: {os_expected_subnet_ids}\n"
                f"  missing:  {os_missing_subnet_ids}"
            )
        )

        # for every missing subnet, create a new port and add it to the server, or add an existing one
        for os_missing_subnet_id in os_missing_subnet_ids:
            os_missing_subnet = os_expected_subnets[os_missing_subnet_id]
            logger.info(f"Will add port with subnet '{os_missing_subnet.name}' to server '{os_server.name}'.")

            # TODO(sprietl): Make name of port and finding more general, to reuse previously created ones
            os_port_name = f"{PORT_NAME_PREFIX}-{os_server.name}-{os_missing_subnet.name}"
            os_port = os_conn.get_port(os_port_name)
            if not os_port:
                logger.info(f"Will create a new port because '{os_port_name}' does not exist.")
                os_port = os_conn.create_port(
                    name=os_port_name,
                    network_id=os_missing_subnet.network_id,
                    # Note(sprietl): For now we only create ports with one IP
                    fixed_ips=[{'subnet_id': os_missing_subnet_id}],
                )

            os_conn.compute.create_server_interface(os_server.id, port_id=os_port.id)
            os_actual_ports.append(os_port)

        # create networking config for each port
        networking_config_handler.create(
            os_ports=os_actual_ports,
            os_subnets=os_expected_subnets,
            config_destination=networking_config_destination,
            config_templates=networking_config_templates,
        )

        # apply networking config
        networking_config_handler.apply()

        logger.debug(f"Wait for {reconciliation_interval}s until reconciliation.")
        time.sleep(reconciliation_interval)


if __name__ == "__main__":
    app()
