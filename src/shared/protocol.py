import struct
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, Tuple

class MoQMessageType(IntEnum):
    
    ANNOUNCE = 0x01
    SUBSCRIBE = 0x02
    OBJECT = 0x03
    ERROR =  0xFF


@dataclass
class MoQMessage:
    msg_type: MoQMessageType
    payload: bytes

    def pack(self) -> bytes:
        """
        Takes the message and turns it into raw bytes for the network.
        Format: [Type (1B)] + [Length (4B)] + [Payload]
        """
        length = len(self.payload)
        #formation of the header of the object and then that is converted to bytes to send alongside the payload 
        header = struct.pack("!B I",self.msg_type,length)

        return header + self.payload


    @classmethod
    def unpack(cls,buffer:bytes) -> Tuple[Optional['MoQMessage'], bytes]:
        """
        Tries to read ONE complete message from the incoming data buffer.
        
        Returns: (Message_Found, Remaining_Buffer)
        """
        HEADER_LENGTH=5

        if len(buffer) < HEADER_LENGTH:
            return None,buffer
        
        msg_type_int,length =struct.unpack("!B I",buffer[:HEADER_LENGTH])

        total_msg_length=HEADER_LENGTH+length

        if len(buffer)<total_msg_length:
            return None,buffer

        payload=buffer[HEADER_LENGTH:total_msg_length]
        remaining_buffer=buffer[total_msg_length:]

        try:
            msg_type = MoQMessageType(msg_type_int)
        except ValueError:
            msg_type = MoQMessageType.ERROR

        return cls(msg_type, payload),remaining_buffer
    




# #so this is the protocol low level network stuff where we convert bytes to objects and objects to bytes
# we are using unpack as a class method that returns the object , cls is the alternate for self in class method and also 
# note that data is like liquid through a pipe , so that is why we wait till we cross 500 bytes and then we send back the re\
# remaining parts of the bytes a