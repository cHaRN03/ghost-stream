import asyncio
import argparse
import logging
import ssl
import cv2
import numpy as np

from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated, QuicEvent

from src.shared.protocol import MoQMessage, MoQMessageType

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("GhostClient")

SERVER_IP = "127.0.0.1"
SERVER_PORT = 4444

class GhostClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_queue = asyncio.Queue()

    def quic_event_received(self, event: QuicEvent):
        self._event_queue.put_nowait(event)

    async def wait_for_next_event(self):
        return await self._event_queue.get()

async def run_streamer(connection: GhostClientProtocol, stream_id: str, fps: int = 30):
    logger.info(f"🎥 STARTING JPEG STREAM: {stream_id}")

    # 1. Announce Room
    announce_msg = MoQMessage(MoQMessageType.ANNOUNCE, stream_id.encode('utf-8'))
    connection._quic.send_stream_data(0, announce_msg.pack())
    connection.transmit()

    # 2. Open Camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Compress to 70% quality JPEG to keep network speed fast
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Show local preview
            cv2.imshow("Streamer Local Preview", frame)
            cv2.waitKey(1)
            
            # Encode frame to JPEG
            result, encoded_image = cv2.imencode('.jpg', frame, encode_param)
            if not result:
                continue

            # Convert to pure bytes
            frame_bytes = encoded_image.tobytes()
            
            # Sanity Check
            if len(frame_bytes) > 60000:
                logger.warning(f"⚠️ JPEG too large ({len(frame_bytes)} bytes)! Might be dropped by MoQMessage length limits.")
            
            # Package and Send
            msg = MoQMessage(MoQMessageType.OBJECT, frame_bytes)
            connection._quic.send_stream_data(0, msg.pack())
            connection.transmit()
            
            await asyncio.sleep(1 / fps) 
            
    except asyncio.CancelledError:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.info("Camera released.")

async def run_viewer(connection: GhostClientProtocol, stream_id: str):
    logger.info(f"👀 JOINING JPEG STREAM: {stream_id}")

    # 1. Subscribe to Room
    sub_msg = MoQMessage(MoQMessageType.SUBSCRIBE, stream_id.encode('utf-8'))
    connection._quic.send_stream_data(0, sub_msg.pack())
    connection.transmit()

    buffer = b""
    window_name = f"Ghost Stream: {stream_id}"
    
    try:
        while True:
            event = await connection.wait_for_next_event()
            
            if isinstance(event, StreamDataReceived):
                buffer += event.data
                
                while True:
                    msg, remaining = MoQMessage.unpack(buffer)
                    if msg is None:
                        break # Need more data for a full frame
                    
                    buffer = remaining
                    
                    if msg.msg_type == MoQMessageType.OBJECT:
                        try:
                            # 1. Convert raw bytes to NumPy array
                            np_arr = np.frombuffer(msg.payload, np.uint8)
                            
                            # 2. Decode JPEG back into an OpenCV image
                            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                            
                            if frame is not None:
                                # 3. Display the video!
                                cv2.imshow(window_name, frame)
                                cv2.waitKey(1)
                        except Exception as e:
                            logger.debug(f"Frame decode error: {e}")
                        
            elif isinstance(event, ConnectionTerminated):
                logger.info("Server closed connection.")
                break

    except asyncio.CancelledError:
        pass
    finally:
        cv2.destroyAllWindows()

async def main():
    parser = argparse.ArgumentParser(description="Ghost Stream Client")
    parser.add_argument('--mode', choices=['streamer', 'viewer'], required=True)
    parser.add_argument('--room', default="demo-1", help="Room ID")
    parser.add_argument('--fps', type=int, default=30, help='Target FPS')
    args = parser.parse_args()

    config = QuicConfiguration(is_client=True)
    config.verify_mode = ssl.CERT_NONE 

    logger.info(f"Connecting to {SERVER_IP}:{SERVER_PORT}...")

    async with connect(
        SERVER_IP, 
        SERVER_PORT, 
        configuration=config, 
        create_protocol=GhostClientProtocol
    ) as connection:
        
        if args.mode == 'streamer':
            await run_streamer(connection, args.room, fps=args.fps)
        else:
            await run_viewer(connection, args.room)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass