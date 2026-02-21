"""
Docker utilities for chaos tests.
Start/stop/restart containers; check if Docker is available.
"""
import logging
import subprocess
import shutil

logger = logging.getLogger(__name__)

CONTAINER_REDIS = "vagus-redis"
CONTAINER_POSTGRES = "vagus-postgres"
CONTAINER_CHROMADB = "chromadb"


def docker_available() -> bool:
    """Check if Docker CLI is available."""
    return shutil.which("docker") is not None


def container_running(container_name: str) -> bool:
    """Check if container is running."""
    if not docker_available():
        return False
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("container_running(%s) failed: %s", container_name, exc)
        return False


def container_stop(container_name: str, timeout: int = 10) -> bool:
    """Stop a container. Returns True if stopped or already stopped."""
    if not docker_available():
        logger.warning("Docker not available")
        return False
    try:
        result = subprocess.run(
            ["docker", "stop", "-t", str(timeout), container_name],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        if result.returncode != 0:
            logger.warning("docker stop %s: %s", container_name, result.stderr or result.stdout)
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("container_stop(%s) failed: %s", container_name, exc)
        return False


def container_start(container_name: str) -> bool:
    """Start a container. Returns True if started successfully."""
    if not docker_available():
        logger.warning("Docker not available")
        return False
    try:
        result = subprocess.run(
            ["docker", "start", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("docker start %s: %s", container_name, result.stderr or result.stdout)
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("container_start(%s) failed: %s", container_name, exc)
        return False


def container_restart(container_name: str) -> bool:
    """Restart a container. Returns True if restarted successfully."""
    if not docker_available():
        logger.warning("Docker not available")
        return False
    try:
        result = subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("docker restart %s: %s", container_name, result.stderr or result.stdout)
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("container_restart(%s) failed: %s", container_name, exc)
        return False
