import socket
import struct
import ssl
from threading import Thread
import select


class SocketClient:

    NO_BUFFERING = 0
    LENGTH_BUFFERING = 1
    DELIMITER_BUFFERING = 2

    def __init__(self, ssl_cert=None, buffering=LENGTH_BUFFERING,
                 delimiter='\n'):
        self.terminated = False
        self.connected = False
        self.ssl_cert = ssl_cert
        self.buffering = buffering
        self.delimiter = delimiter
        self.left = b''
        print("Initialized socket client")

    def connect(self, host, port):
        try:
            self.socket = socket.socket()
            # if using a ssl certificate, wrap the socket using ssl
            if self.ssl_cert:
                self.socket = ssl.wrap_socket(self.socket,
                                              ca_certs=self.ssl_cert,
                                              cert_reqs=ssl.CERT_REQUIRED)
            self.socket.connect((host, port))
            self.connected = True
            return True
        except socket.error:
            print("ERROR: Error while connecting!")
            self.connected = False
            return False

    def start(self):
        print("Client has started")
        Thread(target=self.handle_server).start()

    def disconnect(self):
        print("disconnecting")
        self.connected = False
        self.send("quit")
        self.terminated = True
        self.socket.close()

    def send(self, data):
        try:
            if self.buffering is SocketClient.DELIMITER_BUFFERING:
                msg = (data + self.delimiter).encode()
            elif self.buffering is SocketClient.LENGTH_BUFFERING:
                msg = struct.pack('>I', len(data)) + data.encode()
            else:
                msg = data.encode()
            self.socket.sendall(msg)
        except Exception as e:
            print("ERROR: Error while sending", e)

    def handle_server(self):
        while not self.terminated:
            try:
                read_sockets, write_sockets, in_error = \
                    select.select([self.socket, ], [self.socket, ], [], 5)
            except select.error:
                print("FATAL ERROR: Connection error")
                self.socket.shutdown(2)
                self.socket.close()
            if len(read_sockets) > 0:
                if self.buffering is SocketClient.DELIMITER_BUFFERING:
                    recv, self.left = recvuntil(self.socket, self.delimiter,
                                                self.left)
                elif self.buffering is SocketClient.LENGTH_BUFFERING:
                    raw_msglen = recvall(self.socket, 4)
                    if not raw_msglen:
                        print("Connection closed")
                        self.on_quit()
                        return None
                    msglen = struct.unpack('>I', raw_msglen)[0]
                    recv = recvall(self.socket, msglen)
                elif self.buffering is SocketClient.NO_BUFFERING:
                    recv = self.socket.recv(2048)

                if len(recv) > 0:
                    reply = self.on_receive(recv)
                if len(write_sockets) > 0 and reply:
                    self.socket.send(reply)
        print("finished handling server")

    def on_receive(self, query):
        pass

    def on_quit(self):
        pass


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
    client = SocketClient(buffering=SocketClient.DELIMITER_BUFFERING,
                          delimiter='\r\n')
    client.connect('localhost', 4242)
    client.start()
    client.on_receive = lambda x: print("-->", x)
    while True:
        x = input("> ")
        client.send(x)
