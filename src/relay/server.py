import asyncio
import logging
from typing import Optional

from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated, QuicEvent
from aioquic.quic.connection import QuicConnection


from src.shared.protocol import MoQMessage, MoQMessageType
from src.relay.core import RelayManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("RelayServer")

MANAGER=RelayManager()


class GhostConnectionHandler:

    def __init__(self,connection:QuicConnection):
        self.connection= connection
        self.stream_id:str=None
        self.viewer_queue:Optional[asyncio.Queue] = None
        self.role=None
        self.buffer=b''
        self.task:Optional[asyncio.Task] = None

    def quic_event_received(self,event:QuicEvent):

            if isinstance(event,StreamDataReceived):
                self._handle_incoming_data(event.data)
            elif isinstance(event,ConnectionTerminated):
                # When the connection is terminated we must cleanup internal state
                # (remove streamer rooms, detach viewer queues, cancel tasks).
                self._cleanup()

        
    def _handle_incoming_data(self,data:bytes):
            

           self.buffer += data
           while True:
           
            
            msg,buff = MoQMessage.unpack(self.buffer)

            if msg is None:
                break

            self.buffer=buff
            self._route_message(msg)

        
    def _route_message(self,msg:MoQMessage):

            if msg.msg_type== MoQMessageType.ANNOUNCE:
                sid=msg.payload.decode('utf-8')
                logger.info(f"ANNOUNCE received raw payload bytes: {msg.payload!r}")
                logger.info(f"Decoded SID: {sid!r}")
                if MANAGER.create_stream(sid):
                    self.stream_id=sid
                    self.role="STREAMER"
                else:
                    logger.warning(f"Failed to create stream {sid}. Existing rooms: {list(MANAGER.rooms.keys())}")
                    self.connection.close(error_code=1, frame_type=0, reason_phrase="Stream Exists")

            elif msg.msg_type == MoQMessageType.SUBSCRIBE:
                sid=msg.payload.decode('utf-8')
                


                room=MANAGER.get_room(sid)
                if room:
                    self.stream_id=sid
                    self.role="VIEWER"
                    self.viewer_queue=asyncio.Queue(maxsize=50)

                    room.add_viewer(self.viewer_queue)

                    self.task=asyncio.create_task(self._push_to_client())
                else:
                    self.connection.close(error_code=2, reason_phrase="Stream Not Found")

            elif msg.msg_type == MoQMessageType.OBJECT:
            # Incoming Video Data from a Streamer
                if self.role == 'STREAMER' and self.stream_id:
                    room = MANAGER.get_room(self.stream_id)
                    if room:
                    # Drop the payload into the Actor's inbox. Non-blocking!
                        room.broadcast(msg.payload)

    async def _push_to_client(self):
            """
            Dedicated background worker for a VIEWER.
            Reads from the Viewer's Queue and pushes into the QUIC socket.
            """
            try:
                while True:
                    video_data = await self.viewer_queue.get()
                    
                    # Package it back into our Protocol
                    out_msg = MoQMessage(MoQMessageType.OBJECT, video_data)
                    
                    # Send via QUIC Stream 0
                    self.connection.send_stream_data(stream_id=0, data=out_msg.pack())
                    self.connection.transmit()
                    
            except asyncio.CancelledError:
                # Task was killed (connection dropped)
                pass        

    def _cleanup(self):
            """Fires when the network cable is cut."""
            logger.info(f"Connection lost for {self.role} on stream {self.stream_id}")
            
            if self.role == 'STREAMER' and self.stream_id:
                MANAGER.delete_stream(self.stream_id)
                
            elif self.role == 'VIEWER' and self.stream_id:
                room = MANAGER.get_room(self.stream_id)
                if room and self.viewer_queue:
                    # Tell the Actor to remove us
                    room.remove_viewer(self.viewer_queue)
                if self.task:
                    self.task.cancel()                
                
 # FIX 3: Inherit from QuicConnectionProtocol
class GhostServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        # Initialize the parent class (This sets up self._quic)
        super().__init__(*args, **kwargs)
        self._handler: Optional[GhostConnectionHandler] = None

    def quic_event_received(self, event: QuicEvent):
        # Initialize our handler on the first event
        if not self._handler:
            # self._quic is provided by the parent class
            self._handler = GhostConnectionHandler(self._quic)
        
        # Pass the event to our logic
        self._handler.quic_event_received(event)

async def main():
    config = QuicConfiguration(is_client=False)
    # Ensure certs exist!
    config.load_cert_chain("certs/cert.pem", "certs/key.pem")

    logger.info("Ghost Stream Relay starting on UDP 4444...")
    
    await serve(
        host="0.0.0.0",
        port=4444,
        configuration=config,
        create_protocol=GhostServerProtocol,
    )
    
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutting down.")