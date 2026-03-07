#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2024 CMS Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Cluster management commands for starting/stopping ResourceService on
multiple hosts via SSH.

"""

import gevent.monkey
gevent.monkey.patch_all()  # noqa

import argparse
import logging
import subprocess
import sys
import time

from cms import config, async_config, utf8_decoder


logger = logging.getLogger(__name__)

TMUX_SESSION_NAME = "cms"


def get_resource_service_hosts():
    """Extract hosts and their shards from ResourceService configuration.

    Returns a list of tuples: [(host, shard), ...]
    """
    hosts = []
    for coord, address in async_config.core_services.items():
        if coord.name == "ResourceService":
            hosts.append((address.ip, coord.shard))
    return sorted(hosts, key=lambda x: x[1])


def ssh_execute(host, user, command):
    """Execute a command on a remote host via SSH.

    Args:
        host: The hostname or IP to connect to
        user: The SSH user
        command: The command to execute

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        f"{user}@{host}",
        command
    ]

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "SSH command timed out"
    except Exception as e:
        return False, "", str(e)


def start_with_tmux(host, user, contest_id, shard):
    """Start ResourceService in a tmux session on the remote host.

    If a tmux session named 'cms' exists, it sends Ctrl-C to stop any
    running process and then starts the new ResourceService.
    Otherwise, it creates a new tmux session.

    Args:
        host: The hostname or IP
        user: SSH user
        contest_id: Contest ID to pass to ResourceService
        shard: The shard number for this host

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    check_cmd = f"tmux has-session -t {TMUX_SESSION_NAME} 2>/dev/null"
    session_exists, _, _ = ssh_execute(host, user, check_cmd)

    resource_cmd = f"cmsResourceService {shard} -a {contest_id}"

    if session_exists:
        commands = [
            f"tmux send-keys -t {TMUX_SESSION_NAME} C-c",
            "sleep 1",
            f"tmux send-keys -t {TMUX_SESSION_NAME} '{resource_cmd}' Enter"
        ]
        full_cmd = " && ".join(commands)
    else:
        full_cmd = f"tmux new-session -d -s {TMUX_SESSION_NAME} '{resource_cmd}'"

    return ssh_execute(host, user, full_cmd)


def start_with_systemd(host, user, contest_id, shard):
    """Start ResourceService using systemd user service.

    Creates or updates the systemd user service file and restarts it.

    Args:
        host: The hostname or IP
        user: SSH user
        contest_id: Contest ID to pass to ResourceService
        shard: The shard number for this host

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    service_content = f"""[Unit]
Description=CMS ResourceService shard {shard}
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/env cmsResourceService {shard} -a {contest_id}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target"""

    escaped_content = service_content.replace("'", "'\\''")

    commands = [
        "mkdir -p ~/.config/systemd/user",
        f"echo '{escaped_content}' > ~/.config/systemd/user/cms-resource.service",
        "systemctl --user daemon-reload",
        "systemctl --user restart cms-resource.service"
    ]

    full_cmd = " && ".join(commands)
    return ssh_execute(host, user, full_cmd)


def stop_with_tmux(host, user):
    """Stop ResourceService by killing the tmux session.

    Args:
        host: The hostname or IP
        user: SSH user

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    cmd = f"tmux kill-session -t {TMUX_SESSION_NAME} 2>/dev/null || true"
    return ssh_execute(host, user, cmd)


def stop_with_systemd(host, user):
    """Stop ResourceService by stopping the systemd user service.

    Args:
        host: The hostname or IP
        user: SSH user

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    cmd = "systemctl --user stop cms-resource.service 2>/dev/null || true"
    return ssh_execute(host, user, cmd)


def cluster_start(contest_id, use_systemd=False):
    """Start ResourceService on all configured cluster hosts.

    Args:
        contest_id: Contest ID to pass to ResourceService
        use_systemd: If True, use systemd --user; otherwise use tmux

    Returns:
        True if all hosts started successfully, False otherwise
    """
    hosts = get_resource_service_hosts()
    if not hosts:
        logger.error("No ResourceService hosts found in configuration.")
        return False

    user = config.cluster_ssh_user
    success_count = 0
    mode = "systemd" if use_systemd else "tmux"

    logger.info("Starting ResourceService on %d host(s) using %s...",
                len(hosts), mode)

    for host, shard in hosts:
        logger.info("  Starting on %s (shard %d)...", host, shard)

        if use_systemd:
            ok, out, err = start_with_systemd(host, user, contest_id, shard)
        else:
            ok, out, err = start_with_tmux(host, user, contest_id, shard)

        if ok:
            logger.info("    Started successfully on %s", host)
            success_count += 1
        else:
            logger.error("    Failed on %s: %s", host, err.strip() or "Unknown error")

    logger.info("Started %d/%d hosts successfully.", success_count, len(hosts))
    return success_count == len(hosts)


def cluster_stop(use_systemd=False):
    """Stop ResourceService on all configured cluster hosts.

    Args:
        use_systemd: If True, use systemd --user; otherwise use tmux

    Returns:
        True if all hosts stopped successfully, False otherwise
    """
    hosts = get_resource_service_hosts()
    if not hosts:
        logger.error("No ResourceService hosts found in configuration.")
        return False

    user = config.cluster_ssh_user
    success_count = 0
    mode = "systemd" if use_systemd else "tmux"

    logger.info("Stopping ResourceService on %d host(s) using %s...",
                len(hosts), mode)

    for host, shard in hosts:
        logger.info("  Stopping on %s (shard %d)...", host, shard)

        if use_systemd:
            ok, _, err = stop_with_systemd(host, user)
        else:
            ok, _, err = stop_with_tmux(host, user)

        if ok:
            logger.info("    Stopped successfully on %s", host)
            success_count += 1
        else:
            logger.error("    Failed on %s: %s", host, err.strip() or "Unknown error")

    logger.info("Stopped %d/%d hosts successfully.", success_count, len(hosts))
    return success_count == len(hosts)


def main_start():
    """Entry point for cmsClusterStart command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Start CMS ResourceService on all cluster hosts via SSH.")
    parser.add_argument(
        "contest_id",
        type=utf8_decoder,
        help="Contest ID to pass to ResourceService (or 'ALL' for all contests)"
    )
    parser.add_argument(
        "--systemd",
        action="store_true",
        help="Use systemd --user instead of tmux"
    )

    args = parser.parse_args()

    success = cluster_start(args.contest_id, args.systemd)
    return 0 if success else 1


def main_stop():
    """Entry point for cmsClusterStop command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Stop CMS ResourceService on all cluster hosts via SSH.")
    parser.add_argument(
        "--systemd",
        action="store_true",
        help="Use systemd --user instead of tmux"
    )

    args = parser.parse_args()

    success = cluster_stop(args.systemd)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main_start())
