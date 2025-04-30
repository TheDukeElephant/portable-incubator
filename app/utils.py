import socket
import logging

logger = logging.getLogger(__name__)

def check_connectivity(host="8.8.8.8", port=53, timeout=3):
    """
    Check for network connectivity by attempting to connect to a known host.

    Args:
        host (str): The IP address or hostname of the server to connect to.
                    Defaults to Google's public DNS server.
        port (int): The port number to connect to. Defaults to 53 (DNS).
        timeout (int): Connection timeout in seconds. Defaults to 3.

    Returns:
        bool: True if connection is successful, False otherwise.
    """
    try:
        socket.setdefaulttimeout(timeout)
        # Try connecting to the host on the specified port
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        logger.debug(f"Connectivity check successful: Connected to {host}:{port}")
        return True
    except socket.error as ex:
        logger.warning(f"Connectivity check failed: Could not connect to {host}:{port}. Error: {ex}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during connectivity check: {e}")
        return False

if __name__ == '__main__':
    # Example usage for testing
    if check_connectivity():
        print("Network connection detected.")
    else:
        print("No network connection.")