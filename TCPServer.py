import socket
import select
import hashlib
import pymssql
import random
class ZFChatDB:
    def __init__(self):
        self.db = pymssql.connect("localhost","root","admin","zfchat")
        self.seed = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
    #input a user_name, password which is already encoded in utf-8
    def CreateUser(self, user_name, password):
        #generate random salt
        sa = []
        for i in range(0,10):
            sa.append(random.choice(self.seed))
        salt = ''.join(sa)
        #encode salt to bytes
        salt = salt.encode('utf-8')
        saltedPw = password + salt
        md5 = hashlib.md5(saltedPw).hexdigest()
class ZFChatRoom:
    def __init__(self):
        # All Connections
        self.ConnectionList = []
        # Connections those have not login
        self.unLoginList = []
        # Connections Login, using username as key, easy to locate the connection by username
        self.loginDict = {}
        # Connection mapped by ipv4 address
        self.IPDict = {}
        # max number of connections
        self.maxConnection = 30
        self.receiveBufferSize = 4096
        self.address = ("127.0.0.1", 5050)

        #initialize the sockets
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        #bind the socket, and start listening
        self.sock.bind(self.address)
        self.ConnectionList.append(self.sock)
        self.sock.listen(self.maxConnection)
        # an infinite loop for listening
        while True:
            readSockets, writeSockets, errorSockets = select.select(self.ConnectionList, [], [])
            for sock in readSockets:
                if sock == self.sock:
                    #received a new connection
                    newClient, addr = self.sock.accept()
                    #add this socket to IP dict
                    self.IPDict[newClient] = addr
                    #add this socket to all-connection list
                    self.ConnectionList.append(newClient)
                    #add this socket to unLogin list
                    self.unLoginList.append(newClient)
                    print("New connection from: " + addr[0])
                else:
                    data = sock.recv(self.receiveBufferSize)
                    if len(data) > 0:
                        self.ProcessMsg(data)
                    #if len(data) = 0, then it is a unconnect message
                    else:
                        self.disconnect(sock)

    def broadcast(self, message):
        for sock in self.ConnectionList:
            if sock == self.sock:
                continue
            try:
                sock.send(message.encode())
            except:
                self.disconnect(sock)

    def disconnect(self, sock):
        try:
            sock.close()
            self.ConnectionList.remove(sock)
            self.broadcast("client:" + self.IPDict[sock][0] + " leaves")
            self.IPDict.pop(sock)
        except:
            return
    def ProcessMsg(self, msgbytes):
        #User sign up with a user name and password
        if(msgbytes[0] == 0x01):
            nameAndPw = msgbytes[1:len(msgbytes)].split(bytes([0]))
        #User sign in with a user name and password
        elif(msgbytes[0] == 0x02):
            nameAndPw = msgbytes[1:len(msgbytes)].split(bytes([0]))
        #User message with a sender name, a receiver name, and
        elif(msgbytes[0] == 0x03):
            msgParts = msgbytes[1:len(msgbytes)].split(bytes([0]))
            senderName = msgParts[0]
            receiverName = msgParts[1]
            text = msgParts[2]
            if(self.loginDict.__contains__(receiverName)):
                self.loginDict[receiverName].send(senderName + bytes([0]) + text)
            else:
                pass
        #undefined front byte
        else:
            pass


zfchatroom = ZFChatRoom()
zfchatroom.start()