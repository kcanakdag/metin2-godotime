"""Recognise the one Godot editor-IPC startup error that is never fatal.

A second Godot process cannot bind the editor IPC port while another editor
instance owns it, and a restricted sandbox can refuse the socket outright.
Godot 4.7.2 prints this exact pair and keeps running, so tooling strips only
this signature before applying its "ERROR:" failure gate. Any other error, or
the same error in a non-zero exit, still fails.
"""

EDITOR_SOCKET_PORT_ERROR = (
    'ERROR: Condition "_sock == -1" is true. Returning: FAILED\n'
    "   at: _inet_open (drivers/unix/net_socket_unix.cpp:288)\n"
    'ERROR: Condition "err != OK" is true. Returning: ERR_CANT_CREATE\n'
    "   at: listen (core/io/tcp_server.cpp:56)"
)


def strip_editor_socket_port_error(output: str) -> str:
    """Remove the harmless editor-IPC bind failure from captured log output."""
    return output.replace(EDITOR_SOCKET_PORT_ERROR, "")
