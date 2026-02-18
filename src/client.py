import asyncio
import argparse
import logging
import time
import os
import random
import ssl

from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated, QuicEvent

from src.shared.protocol import MoQMessage, MoQMessageType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("GhostClient")

# --- Configuration ---
SERVER_IP = "127.0.0.1"
SERVER_PORT = 4444

# --- Custom Protocol to Handle Events ---
class GhostClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We create a queue to store incoming events (Video Frames)
        self._event_queue = asyncio.Queue()

    def quic_event_received(self, event: QuicEvent):
        # whenever a packet arrives, put it in the queue
        logger.debug(f"Client protocol queued event: {event!r}")
        self._event_queue.put_nowait(event)

    async def wait_for_next_event(self):
        # This is the helper method we were missing!
        return await self._event_queue.get()

# --- Roles ---

async def run_streamer(connection: GhostClientProtocol, stream_id: str, fps: int = 30, count: int = 100):
    logger.info(f"🎥 STARTING STREAM: {stream_id}")

    # 1. Send ANNOUNCE once
    announce_msg = MoQMessage(MoQMessageType.ANNOUNCE, stream_id.encode('utf-8'))
    connection._quic.send_stream_data(0, announce_msg.pack())
    connection.transmit()

    # 1.a Send an initial OBJECT so viewers can immediately detect the stream
    initial_frame = f"Initial Frame | Timestamp {time.time()}".encode('utf-8')
    init_msg = MoQMessage(MoQMessageType.OBJECT, initial_frame)
    connection._quic.send_stream_data(0, init_msg.pack())
    connection.transmit()
    logger.info("Sent initial OBJECT after ANNOUNCE")

    # 2. Stream Loop: send `count` frames (or infinite if count == 0)
    frame_count = 0
    try:
        while True:
            if count > 0 and frame_count >= count:
                logger.info(f"Completed sending {count} frames. Stopping stream.")
                break

            frame_data = f"Frame {frame_count} | Timestamp {time.time()}".encode('utf-8')
            msg = MoQMessage(MoQMessageType.OBJECT, frame_data)

            connection._quic.send_stream_data(0, msg.pack())
            connection.transmit()

            logger.info(f"Sent: Frame {frame_count}")
            frame_count += 1
            await asyncio.sleep(1 / max(1, fps))

    except asyncio.CancelledError:
        logger.info("Stream stopped.")

async def run_viewer(connection: GhostClientProtocol, stream_id: str):
    logger.info(f"👀 JOINING STREAM: {stream_id}")

    # 1. Send Subscribe
    sub_msg = MoQMessage(MoQMessageType.SUBSCRIBE, stream_id.encode('utf-8'))
    connection._quic.send_stream_data(0, sub_msg.pack())
    connection.transmit()

    # 2. Listen Loop
    buffer = b""
    try:
        while True:
            # FIX: Use our new custom method
            event = await connection.wait_for_next_event()
            logger.debug(f"Viewer received event: {event!r}")
            
            if isinstance(event, StreamDataReceived):
                buffer += event.data
                logger.debug(f"StreamDataReceived on stream {event.stream_id}, {len(event.data)} bytes")
                while True:
                    msg, remaining = MoQMessage.unpack(buffer)
                    if msg is None:
                        break
                    buffer = remaining
                    
                    if msg.msg_type == MoQMessageType.OBJECT:
                        print(f"📺 WATCHING: {msg.payload.decode('utf-8')}")
            
            elif isinstance(event, ConnectionTerminated):
                logger.info("Server closed connection.")
                break

    except asyncio.CancelledError:
        logger.info("Viewer disconnected.")

async def main():
    parser = argparse.ArgumentParser(description="Ghost Stream Client")
    parser.add_argument('--mode', choices=['streamer', 'viewer'], required=True)
    parser.add_argument('--room', default="room-9956", help="Room ID")
    parser.add_argument('--fps', type=int, default=30, help='Frames per second for streamer')
    parser.add_argument('--count', type=int, default=500, help='Number of frames to send (0 = infinite)')
    args = parser.parse_args()

    config = QuicConfiguration(is_client=True)
    
    # --- FIX: Disable Certificate Verification for Localhost ---
    # We are telling the client: "It's okay if the server's ID card is self-printed."
    config.verify_mode = ssl.CERT_NONE 
    # -----------------------------------------------------------

    logger.info(f"Connecting to {SERVER_IP}:{SERVER_PORT}...")

    # Enable debug logging for viewer to help diagnose missing frames
    if args.mode == 'viewer':
        logger.setLevel(logging.DEBUG)

    async with connect(
        SERVER_IP, 
        SERVER_PORT, 
        configuration=config, 
        create_protocol=GhostClientProtocol
    ) as connection:
        
        if args.mode == 'streamer':
            await run_streamer(connection, args.room, fps=args.fps, count=args.count)
        else:
            await run_viewer(connection, args.room)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass