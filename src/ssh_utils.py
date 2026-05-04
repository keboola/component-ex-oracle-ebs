"""SSH private-key parsing helpers.

Vendored from component-elasticsearch/src/client/ssh_utils.py — the canonical
Keboola helper for the `ssh-editor` UI element. The platform sometimes returns
the private key base64-encoded; this module accepts either form.
"""

import base64
import binascii
import contextlib
from io import StringIO

import paramiko


class SSHException(Exception):
    pass


def get_private_key(input_key: str, private_key_password: str | None) -> paramiko.PKey:
    key = _get_decoded_key(input_key)
    try:
        # PKey.from_private_key auto-detects RSA, ECDSA, and Ed25519 formats.
        if private_key_password:
            return paramiko.PKey.from_private_key(StringIO(key), password=private_key_password)
        return paramiko.PKey.from_private_key(StringIO(key))
    except paramiko.ssh_exception.SSHException as pkey_error:
        raise SSHException("Invalid private key") from pkey_error


def _get_decoded_key(input_key: str) -> str:
    """Accept a private key in raw PEM form OR base64-encoded PEM."""
    b64_decoded_input_key = ""
    with contextlib.suppress(binascii.Error):
        b64_decoded_input_key = base64.b64decode(input_key, validate=True).decode("utf-8")

    is_valid_b64, message_b64 = _validate_ssh_private_key(b64_decoded_input_key)
    is_valid, message = _validate_ssh_private_key(input_key)
    if is_valid_b64:
        return b64_decoded_input_key
    if is_valid:
        return input_key
    raise SSHException("\n".join([message, message_b64]))


def _validate_ssh_private_key(ssh_private_key: str) -> tuple[bool, str]:
    if "\n" not in ssh_private_key:
        return False, "SSH private key is invalid — make sure newlines are preserved."
    return True, ""
