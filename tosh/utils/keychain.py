"""
Keychain credential access for tosh daemon.
Uses macOS security command to retrieve passwords securely.
"""

import subprocess
import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "tosh-comms-db"
ACCOUNT_NAME = "postgres"


class KeychainError(Exception):
    """Raised when Keychain access fails."""
    pass


def get_db_password() -> str:
    """
    Retrieve database password from macOS Keychain.

    Returns:
        The password string.

    Raises:
        KeychainError: If password cannot be retrieved.
    """
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s", SERVICE_NAME,
                "-a", ACCOUNT_NAME,
                "-w"  # Output password only
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "could not be found" in stderr.lower():
                raise KeychainError(
                    f"Credential not found. Run setup-keychain.sh first. "
                    f"Service: {SERVICE_NAME}, Account: {ACCOUNT_NAME}"
                )
            raise KeychainError(f"Keychain access failed: {stderr}")

        password = result.stdout.strip()
        if not password:
            raise KeychainError("Retrieved password is empty")

        return password

    except subprocess.TimeoutExpired:
        raise KeychainError("Keychain access timed out (possible prompt waiting)")
    except FileNotFoundError:
        raise KeychainError("security command not found (not on macOS?)")


def test_keychain_access() -> bool:
    """
    Test if Keychain credentials are accessible.

    Returns:
        True if credentials accessible, False otherwise.
    """
    try:
        get_db_password()
        return True
    except KeychainError as e:
        logger.warning(f"Keychain access test failed: {e}")
        return False
