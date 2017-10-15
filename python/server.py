import socket
import select
import ssl
import struct
import threading
from threading import Thread
import logging as log


class SocketServer:

    NO_BUFFERING = 0
    LENGTH_BUFFERING = 1
    DELIMITER_BUFFERING = 2

    def __init__(self, ssl_cert=None, ssl_key=None, buffering=LENGTH_BUFFERING,
                 delimiter='\n'):
        self.terminated = False
        self.connected = False
        self.buffering = buffering
        self.ssl_cert, self.ssl_key = ssl_cert, ssl_key
        self.delimiter = delimiter
        log.debug("Initialized socket server")

    def connect(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if self.ssl_cert and self.ssl_key:
            self.socket = ssl.wrap_socket(self.socket,
                                          certfile=self.ssl_cert,
                                          keyfile=self.ssl_key,
                                          server_side=True)
        try:
            self.socket.bind((host, port))
        except socket.error as e:
            log.critical("Error: %s", str(e))
        self.socket.listen(5)

    def start(self):
        Thread(target=self.wait_for_connections).start()

    def wait_for_connections(self):
        while not self.terminated:
            self.accept_connection()

    def accept_connection(self):
        if self.terminated:
            return
        try:
            conn, addr = self.socket.accept()
        except OSError as e:
            log.error("OSError while accepting connection: %s", str(e))
            return
        Thread(target=self.pre_handle_client, args=(conn, addr)).start()

    def clean_up(self):
        self.terminated = True
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

    def pre_handle_client(self, conn, addr):
        log.info("Established connection to %s", addr)
        client = ClientConnection(conn, addr, self.buffering, self.delimiter)
        connected = self.on_connect(client)

        while not self.terminated and connected:
            try:
                read, write, error = select.select([client.conn, ],
                                                   [client.conn, ],
                                                   [], 5)
            except (select.error, ValueError):
                log.warn("FATAL ERROR: Connection error %s", addr)
                self.on_disconnect(client)
                break
            if len(read) > 0:
                text = client.recv()
                if text is None:
                    log.critical("no text --> disconnecting")
                    self.on_disconnect(client)
                    break
                log.debug("Received: %s %s", text, addr)
                try:
                    reply = self.on_receive(client, text)
                except TypeError:
                    pass
                else:
                    if reply is not None:
                        client.send(reply)

        log.critical("Terminating connection with %s", addr)
        client.quit()

    def on_receive(self, client, query):
        return query

    def on_connect(self, client):
        return True

    def on_disconnect(self, client):
        pass


class ClientConnection:

    def __init__(self, conn, addr, buffering, delimiter):
        self.conn = conn
        self.addr = addr
        self.lock = threading.Lock()
        self.buffering, self.delimiter = buffering, delimiter
        self.left = b''

    def ask(self, key, question):
        self.send(key, question)
        self.conn.settimeout(2)
        return self.recv()

    def recv(self):
        try:
            if self.buffering is SocketServer.DELIMITER_BUFFERING:
                recv, self.left = recvuntil(self.conn, self.delimiter,
                                            self.left)
            elif self.buffering is SocketServer.LENGTH_BUFFERING:
                raw_msglen = recvall(self.conn, 4)
                if not raw_msglen:
                    log.debug("%s No msglen: EOF", self.addr)
                    return None
                msglen = struct.unpack('>I', raw_msglen)[0]
                recv = recvall(self.conn, msglen)
            else:
                recv = self.conn.recv(1024)
            return recv.decode("utf-8")
        except Exception as e:
            log.critical("%s Error while receiving: %s", self.addr, str(e))
            return None

    def send(self, query):
        if self.buffering is SocketServer.DELIMITER_BUFFERING:
            msg = (query + self.delimiter).encode()
        elif self.buffering is SocketServer.LENGTH_BUFFERING:
            msg = struct.pack('>I', len(query)) + query.encode()
        else:
            msg = query.encode()
        with self.lock:
            try:
                self.conn.sendall(msg)
            except Exception as e:
                log.debug("%s Failed to send %s: %s", self.addr, msg, e)

    def on_recv(self):
        pass

    def quit(self):
        self.conn.close()


def recvall(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data


def recvuntil(sock, delimiter, left_over):
    data = left_over
    left = b''
    while True:
        packet = sock.recv(512)
        if not packet:
            return None
        data += packet
        idx = data.find(delimiter.encode())
        if idx >= 0:
            data = data[:idx]
            left = data[idx+len(delimiter):]
            break
    return data, left

if __name__ == '__main__':
    log.basicConfig(level=log.DEBUG)
    server = SocketServer(buffering=SocketServer.DELIMITER_BUFFERING,
                          delimiter='\r\n')
    server.connect('localhost', 4242)
    server.start()
