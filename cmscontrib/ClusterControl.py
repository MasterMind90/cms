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
import json
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

from cms import config, async_config, utf8_decoder
from cms.db import is_contest_id


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


def scp_copy(host, user, local_path, remote_path):
    """Copy a file to a remote host via SCP.

    Args:
        host: The hostname or IP to copy to
        user: The SSH user
        local_path: Local file path to copy
        remote_path: Remote destination path

    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
    """
    scp_cmd = [
        "scp",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        local_path,
        f"{user}@{host}:{remote_path}"
    ]

    try:
        result = subprocess.run(
            scp_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "SCP command timed out"
    except Exception as e:
        return False, "", str(e)


def is_localhost(host):
    """Check if the given host refers to the local machine.

    Args:
        host: Hostname or IP address to check

    Returns:
        True if host is localhost, False otherwise
    """
    localhost_names = {'localhost', '127.0.0.1', '::1'}

    if host.lower() in localhost_names:
        return True

    try:
        local_hostname = socket.gethostname()
        if host.lower() == local_hostname.lower():
            return True
        local_fqdn = socket.getfqdn()
        if host.lower() == local_fqdn.lower():
            return True
    except Exception:
        pass

    return False


def get_local_ip():
    """Get the local IP address that remote hosts can reach.

    Uses the socket connection trick to determine the outbound IP address,
    which is the IP that remote hosts should use to connect back to this host.

    Returns:
        The local IP address as a string
    """
    try:
        # Create a socket to determine the outbound IP
        # This doesn't actually send any data
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback to hostname resolution
        return socket.gethostbyname(socket.gethostname())


def rewrite_database_host_in_config(config_path, new_host):
    """Create a modified config file with database host replaced.

    Reads the config file, replaces localhost/127.0.0.1 in the database
    connection string with the specified host, and writes to a temp file.

    Args:
        config_path: Path to the original config file
        new_host: The host IP to use instead of localhost

    Returns:
        Tuple of (temp_file_path, original_host) or (None, None) if no change needed
    """
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
    except Exception as e:
        logger.error("Failed to read config file for rewriting: %s", e)
        return None, None

    database_str = config_data.get('database', '')
    if not database_str:
        logger.warning("No 'database' field found in config, skipping rewrite.")
        return None, None

    # Pattern to match localhost or 127.0.0.1 in the database connection string
    # Format: postgresql+psycopg2://user:pass@host:port/dbname
    pattern = r'(@)(localhost|127\.0\.0\.1)(:\d+|/)'
    match = re.search(pattern, database_str)

    if not match:
        logger.info("Database host is not localhost, no rewrite needed.")
        return None, None

    original_host = match.group(2)
    new_database_str = re.sub(pattern, rf'\g<1>{new_host}\g<3>', database_str)

    config_data['database'] = new_database_str

    # Create a temporary file with the modified config
    try:
        fd, temp_path = tempfile.mkstemp(suffix='.conf', prefix='cms_cluster_')
        with os.fdopen(fd, 'w') as f:
            json.dump(config_data, f, indent=4)
        return temp_path, original_host
    except Exception as e:
        logger.error("Failed to create temporary config file: %s", e)
        return None, None


def distribute_config(config_path):
    """Copy the config file to all ResourceService hosts.

    Before copying, rewrites the database connection string to replace
    localhost with the local machine's IP address, so remote hosts can
    connect back to the database.

    Args:
        config_path: Path to the local config file to copy

    Returns:
        Tuple of (success: bool, copied_count: int, total_count: int)
    """
    hosts = get_resource_service_hosts()
    if not hosts:
        logger.warning("No ResourceService hosts found for config distribution.")
        return True, 0, 0

    user = config.cluster_ssh_user

    # Get unique hosts (multiple shards may be on same host)
    unique_hosts = sorted(set(host for host, shard in hosts))

    # Filter out localhost
    remote_hosts = [h for h in unique_hosts if not is_localhost(h)]

    if not remote_hosts:
        logger.info("No remote hosts to copy config to (all hosts are localhost).")
        return True, 0, len(unique_hosts)

    # Rewrite database host in config for remote hosts
    local_ip = get_local_ip()
    temp_config_path, original_host = rewrite_database_host_in_config(
        config_path, local_ip)

    if temp_config_path:
        logger.info("Rewriting database host: %s -> %s", original_host, local_ip)
        source_path = temp_config_path
    else:
        # No rewrite needed or failed, use original config
        source_path = config_path

    logger.info("Copying config file to %d remote host(s)...", len(remote_hosts))

    copied_count = 0
    try:
        for host in remote_hosts:
            logger.info("  Copying to %s...", host)

            ok, out, err = scp_copy(host, user, source_path, config_path)

            if ok:
                logger.info("    Config copied successfully to %s", host)
                copied_count += 1
            else:
                logger.error("    Failed to copy config to %s: %s",
                            host, err.strip() or "Unknown error")
                return False, copied_count, len(remote_hosts)
    finally:
        # Clean up temporary config file
        if temp_config_path and os.path.exists(temp_config_path):
            try:
                os.remove(temp_config_path)
            except Exception:
                pass

    logger.info("Config copied to %d/%d remote hosts.", copied_count, len(remote_hosts))
    return True, copied_count, len(remote_hosts)


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


def cluster_start(contest_id, use_systemd=False, copy_config=True,
                  config_path=None):
    """Start ResourceService on all configured cluster hosts.

    Args:
        contest_id: Contest ID to pass to ResourceService
        use_systemd: If True, use systemd --user; otherwise use tmux
        copy_config: If True, copy config file to remote hosts first
        config_path: Explicit path to config file (uses auto-detected if None)

    Returns:
        True if all hosts started successfully, False otherwise
    """
    # Check if contest exists (skip for "ALL" mode)
    if contest_id != "ALL":
        try:
            contest_id_int = int(contest_id)
        except ValueError:
            logger.error("Invalid contest id '%s'. Must be an integer or 'ALL'.",
                        contest_id)
            return False

        if not is_contest_id(contest_id_int):
            logger.error("Contest with id %d does not exist. "
                        "Please check the contest id and try again.",
                        contest_id_int)
            return False
        logger.info("Contest %d is available.", contest_id_int)

    hosts = get_resource_service_hosts()
    if not hosts:
        logger.error("No ResourceService hosts found in configuration.")
        return False

    # Copy config to remote hosts before starting services
    if copy_config:
        if config_path is None:
            config_path = config.config_file_path
            if config_path is None:
                logger.error("Cannot determine config file path. "
                           "Use --config-path to specify explicitly, "
                           "or --no-copy-config to skip.")
                return False

        if not os.path.isfile(config_path):
            logger.error("Config file not found: %s", config_path)
            return False

        logger.info("Config file: %s", config_path)

        success, copied, total = distribute_config(config_path)
        if not success:
            logger.error("Config distribution failed. Aborting cluster start.")
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

        if out.strip():
            logger.info("    stdout: %s", out.strip())
        if err.strip():
            logger.info("    stderr: %s", err.strip())

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
            ok, out, err = stop_with_systemd(host, user)
        else:
            ok, out, err = stop_with_tmux(host, user)

        if ok:
            logger.info("    Stopped successfully on %s", host)
            success_count += 1
        else:
            logger.error("    Failed on %s: %s", host, err.strip() or "Unknown error")

        if out.strip():
            logger.info("    stdout: %s", out.strip())
        if err.strip():
            logger.info("    stderr: %s", err.strip())

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
    parser.add_argument(
        "--no-copy-config",
        action="store_true",
        help="Skip copying config file to remote hosts before starting"
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Explicit path to config file to copy (default: auto-detect)"
    )

    args = parser.parse_args()

    success = cluster_start(
        args.contest_id,
        use_systemd=args.systemd,
        copy_config=not args.no_copy_config,
        config_path=args.config_path
    )
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
