import socket
import select
import hashlib
import pymysql
import random
from enum import Enum
class MessageType(Enum):
    SignUp = 0x01
    SignIn = 0x02
    PrivateMS = 0x03
    RoomMS = 0x04
    CreateLink = 0x05
    DeleteLink = 0x06
    Connected = 0xff
    ServerInfo = 0xfe
    SignInSucceed = 0xf0
    SignUpSucceed = 0xe0
    ContactorList = 0xf1
    NewContactor = 0xf2
class ZFPacket:
    def __init__(self,type = None,Msgs = None,pbytes = None):
        self.charset = 'utf-8'
        self.Msgs = []
        if pbytes == None:
            self.type = type
            self.Msgs = Msgs
        else:
            self.type = MessageType(pbytes[0])
            cs = pbytes[3:].split(bytes([0]))
            for c in cs:
                self.Msgs.append(c.decode(self.charset))
    def GetBytes(self):
        msgBytes = bytes()
        if(len(self.Msgs) > 0):
            msgBytes += self.Msgs[0].encode(self.charset)
        for i in range(1, len(self.Msgs)):
            msgBytes += bytes([0])
            msgBytes += self.Msgs[i].encode(self.charset)
        msgBytes = bytes([ self.type.value, int((len(msgBytes) + 3) / 256), int((len(msgBytes) + 3) % 256) ])\
            + msgBytes
        return msgBytes
class ZFChatDB:
    def __init__(self):
        self.db = pymysql.connect("localhost","root","admin","zfchat")
        self.seed = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
        self.charset = 'utf-8'
    # input a user_name, password which is already encoded in utf-8
    def CreateUser(self, user_name, password):
        # generate random salt
        sa = []
        for i in range(0,10):
            sa.append(random.choice(self.seed))
        salt = ''.join(sa)
        saltedPw = password + salt
        # use hashlib to calculate the salted md5 value
        md5 = hashlib.md5(saltedPw.encode(self.charset)).hexdigest()
        cursor = self.db.cursor()
        cursor.callproc('create_user',args = (user_name,salt,md5,0,))
        self.db.commit()
        cursor.execute("select @_create_user_3")
        result = cursor.fetchone()[0]
        if result == 'ok':
            r = True
        else:
            r = False
        return r,result
    #create links between two user
    #return exec info
    def CreateLink(self, user_name_1, user_name_2):
        cursor = self.db.cursor()
        cursor.callproc('create_link',(user_name_1,user_name_2,0))
        self.db.commit()
        cursor.execute("select @_create_link_2")
        info = cursor.fetchone()[0]
        if info == 'ok':
            return True, info
        else:
            return False, info
    #delete links between two user
    def DeleteLink(self, u_name_1, u_name_2):
        cursor = self.db.cursor()
        cursor.callproc('remove_link', (u_name_1, u_name_2, 0))
        self.db.commit()
        cursor.execute("select @_remove_link_2")
        info = cursor.fetchone()[0]
        if info == 'ok':
            return True, info
        else:
            return False, info
    def SignInAuth(self, user_name, password):
        cursor = self.db.cursor()
        cursor.callproc('get_salt',(user_name,0))
        salt = cursor.fetchone()
        if salt == None:
            return  False,None
        saltedPw = password + salt[0]
        md5 = hashlib.md5(saltedPw.encode(self.charset)).hexdigest()
        cursor.callproc('auth',(user_name,md5,0,))
        result = cursor.fetchone()[0]
        if result == 1:
            cursor.callproc('get_contactors',(user_name,0,))
            contactors = cursor.fetchall()
            clist = []
            for i in range(len(contactors)):
                clist.append(contactors[i][0])
            return True,clist
        else:
            return False,None
    def SaveMessage(self, s_user, r_user, msg):
        cursor = self.db.cursor()
        cursor.callproc('store_message',(s_user,r_user,msg))
        self.db.commit()

    def SaveUnreceivedMessage(self, s_user, r_user, msg):
        cursor = self.db.cursor()
        cursor.callproc('store_unreceived_message',(s_user,r_user,msg))
        self.db.commit()

    def FetchUnreceivedMessage(self, user):
        cursor = self.db.cursor()
        cursor.callproc('fetch_unreceived_message',(user,0))
        allStored = cursor.fetchall()
        allmsg = []
        for i in range(len(allStored)):
            allmsg.append(allStored[i][0:3])
        self.db.commit()
        return  allmsg

'''
    Defining the protocal as follows:
        Client to Server:
            Sign up [0x01] [Len_1] [Len_0] Name [0] Password
            Sign in [0x02] [Len_1] [Len_0] Name [0] Password
            Send Ms [0x03] [Len_1] [Len_0] Name_1 [0] Name_2 [0] Message
        Server to Client:
            Connected [0xff] 
            Login Failed [0xfe] + [0x0] [0x11] "wrong password"                For the whole length = 17
            Login success [0xf0] [Len_1] [Len_0] Name1 [0] Name2 [0] Name3 [0] .... [0] NameN
            Contactors [0xf1] [Len_1] [Len_0] Name1 [0] Name2 [0] Name3 [0] .... [0] NameN
             
'''
class ZFChatRoom:
    def __init__(self):
        # All Connections
        self.ConnectionList = []
        # Connections those have not login
        self.unLoginList = []
        # Connections Login, using username as key, easy to locate the connection by username
        self.loginDict = {}
        self.sockDict = {}
        # Connection mapped by ipv4 address
        self.IPDict = {}
        # max number of connections
        self.maxConnection = 30
        self.receiveBufferSize = 4096
        self.address = ("127.0.0.1", 5050)
        self.chatDB = ZFChatDB()
        # initialize the sockets
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        #b ind the socket, and start listening
        self.sock.bind(self.address)
        self.ConnectionList.append(self.sock)
        self.sock.listen(self.maxConnection)
        # an infinite loop for listening
        while True:
            readSockets, writeSockets, errorSockets = select.select(self.ConnectionList, [], [])
            for sock in readSockets:
                if sock == self.sock:
                    # received a new connection
                    newClient, addr = self.sock.accept()
                    # add this socket to IP dict
                    self.IPDict[newClient] = addr
                    # add this socket to all-connection list
                    self.ConnectionList.append(newClient)
                    # add this socket to unLogin list
                    self.unLoginList.append(newClient)
                    # send 0xff to the client, tell it it's connected
                    newClient.send(ZFPacket(MessageType.Connected,[]).GetBytes())
                    print("New connection from: " + addr[0])
                else:
                    try:
                        data = sock.recv(self.receiveBufferSize)
                    except:
                        self.disconnect(sock)
                        continue
                    print(data)
                    if len(data) > 0:
                        start = 0
                        while start < len(data):
                            dataPiece = data[start: data[1] * 256 + data[2]]
                            self.ProcessMsg(dataPiece, sock)
                            start = len(dataPiece)
                    # if len(data) = 0, then it is a unconnect message
                    else:
                        self.disconnect(sock)

    def broadcast(self, message):
        for sock in self.loginDict.values():
            try:
                sock.send(message)
            except:
                self.disconnect(sock)

    def disconnect(self, sock):
        try:
            sock.close()
            self.ConnectionList.remove(sock)
            if(self.unLoginList.__contains__(sock)):
                self.unLoginList.remove(sock)
            #if it is a login sock, then pop it from two dicts
            if(self.sockDict.__contains__(sock)):
                name = self.sockDict.pop(sock)
                self.loginDict.pop(name)
            self.IPDict.pop(sock)
        except:
            return
    def ProcessMsg(self, msgbytes, sender):
        print("received msg:",msgbytes) #for debug
        # User sign up with a user name and password
        packet = ZFPacket(pbytes=msgbytes)
        if packet.type == MessageType.SignUp:
            nameAndPw = packet.Msgs
            result,info = self.chatDB.CreateUser(nameAndPw[0],nameAndPw[1])
            if result == True:
                if self.unLoginList.__contains__(sender):
                    self.unLoginList.remove(sender)
                self.loginDict[nameAndPw[0]] = sender
                self.sockDict[sender] = nameAndPw[0]
                sender.send(ZFPacket(MessageType.SignInSucceed, []).GetBytes())
            else:
                pass
            sender.send(ZFPacket(MessageType.ServerInfo,[info]).GetBytes())
        # User sign in with a user name and password
        elif packet.type == MessageType.SignIn:
            nameAndPw = packet.Msgs
            result, contactorList = self.chatDB.SignInAuth(nameAndPw[0],nameAndPw[1])
            print("contactorList",contactorList)
            if result:
                if self.unLoginList.__contains__(sender):
                    self.unLoginList.remove(sender)
                self.loginDict[nameAndPw[0]] = sender
                self.sockDict[sender] = nameAndPw[0]
                #
                sendingBytes = ZFPacket(MessageType.SignInSucceed,contactorList).GetBytes()
                sender.send(sendingBytes)
                sender.send(ZFPacket(MessageType.ServerInfo,['Sign in success!']).GetBytes())
                unreceivedMsgs = self.chatDB.FetchUnreceivedMessage(nameAndPw[0])
                print("unreceivedMsgs",unreceivedMsgs)
                for i in range(len(unreceivedMsgs)):
                    sender.send(ZFPacket(MessageType.PrivateMS,unreceivedMsgs[i]).GetBytes())
            else:
                sender.send(ZFPacket(MessageType.ServerInfo, ['Sign in failed!']).GetBytes())
        # User message with a sender name, a receiver name, and
        elif packet.type == MessageType.PrivateMS:
            sender.send(msgbytes)
            self.chatDB.SaveMessage(packet.Msgs[0], packet.Msgs[1], packet.Msgs[2])
            if(self.loginDict.__contains__(packet.Msgs[1])):
                try:
                    self.loginDict[packet.Msgs[1]].send(msgbytes)
                except:
                    self.disconnect(self.loginDict[packet.Msgs[1]])
            else:  #receiver is not currently online
                self.chatDB.SaveUnreceivedMessage(packet.Msgs[0], packet.Msgs[1], packet.Msgs[2])
        elif packet.type == MessageType.RoomMS:
            self.chatDB.SaveMessage(packet.Msgs[0], '__AllPeople__', packet.Msgs[1])
            self.broadcast(packet.GetBytes())
        elif packet.type == MessageType.CreateLink:
            result,info = self.chatDB.CreateLink(packet.Msgs[0], packet.Msgs[1])
            if result== True:
                sender.send(ZFPacket(MessageType.NewContactor,[packet.Msgs[1]]).GetBytes())
            sender.send(ZFPacket(MessageType.ServerInfo, [info]).GetBytes())
        elif packet.type == MessageType.DeleteLink:
            result, info = self.chatDB.DeleteLink(packet.Msgs[0], packet.Msgs[1])
            sender.send(ZFPacket(MessageType.ServerInfo, [info]).GetBytes())
        # undefined front byte
        else:
            pass

ZFChatRoom().start()

#zfchatdb = ZFChatDB()
#(zfchatdb.SignInAuth("zf".encode("utf-8"),"zhengfei".encode("utf-8")))