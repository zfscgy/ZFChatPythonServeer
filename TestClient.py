import sys
import socket
import select
import threading

class MessageSender(threading.Thread):
    def run(self):
        while True:
            message = input()
            sock.send(message.encode())
HOST,PORT = "127.0.0.1",5050
bufferSize = 4096
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
    sock.connect((HOST,PORT))
    readList = [sock]
    MessageSender().start()
    while True:
        read, write, error = select.select(readList, [], [])
        for socket in read:
            if socket == sock:
                data = socket.recv(bufferSize).decode()
                print(data)

