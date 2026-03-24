import os
import telnetlib
import collections
import socket
import threading
from threading import Thread
from typing import Tuple


class TelnetClient:
    def __init__(self, host='localhost', port=24, max_lines=200):
        self.host = host
        self.port = port
        self.max_lines = max_lines
        self.telnet = None
        self.buffer = collections.deque(maxlen=max_lines)
        self.server_socket = None
        self.client_socket = None
        self.lock = threading.Lock()

    def connect(self):
        self.telnet = telnetlib.Telnet(self.host, self.port)
        self.telnet.write(b"activate\n")

    def read_output(self):
        if not self.telnet:
            raise ConnectionError("Not connected to the Telnet server.")

        while True:
            output = self.telnet.read_very_eager().decode('utf-8')
            lines = output.splitlines()
            with self.lock:
                self.buffer.extend(lines)

    def get_last_lines(self):
        with self.lock:
            return list(self.buffer)

    def start_socket_server(self, socket_host='localhost', socket_port=9999):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((socket_host, socket_port))
        self.server_socket.listen(1)
        print(f"Socket server started on {socket_host}:{socket_port}")
        while True:
            self.client_socket, _ = self.server_socket.accept()
            with self.lock:
                data = "\n".join(self.buffer)
            self.client_socket.sendall(data.encode('utf-8'))
            self.client_socket.close()

    def close(self):
        if self.telnet:
            self.telnet.close()
            self.telnet = None
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None


def start_telnet_client() -> tuple[TelnetClient, Thread, Thread]:
    telnet_host = os.getenv('TELNET_HOST', 'localhost')
    telnet_port = int(os.getenv('TELNET_PORT', 24))

    print(f"Connecting to {telnet_host}:{telnet_port}")

    client = TelnetClient(host=telnet_host, port=telnet_port)
    client.connect()

    telnet_thread = threading.Thread(target=client.read_output, daemon=True)
    telnet_thread.start()

    socket_thread = threading.Thread(target=client.start_socket_server, daemon=True)
    socket_thread.start()

    return client, telnet_thread, socket_thread


if __name__ == "__main__":
    first_client, telnet_thread, socket_thread = start_telnet_client()

    try:
        telnet_thread.join()
        socket_thread.join()
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        print("Last 200 lines:")
        print("\n".join(first_client.get_last_lines()))
        first_client.close()
