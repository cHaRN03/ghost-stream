import asyncio
import logging
from typing import Dict, Set
from dataclasses import dataclass,field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RelayCore")



class MsgJoin:
    def __init__(self,viewer_queue:asyncio.Queue):
        self.viewer_queue=viewer_queue

class MsgLeave:
    def __init__(self,viewer_queue:asyncio.Queue):
        self.viewer_queue=viewer_queue

class MsgBroadcast:
    def __init__(self,data:bytes):
        self.data=data

class MsgStop:
    def __init__(self):
        pass


class StreamRoomActor:
    
    def __init__(self,stream_id:str):
        
        self._msg_inbox=asyncio.Queue()
        self.stream_id:str =stream_id
        self.viewers: Set[asyncio.Queue]=set()

        self.task=asyncio.create_task(self._loop())
        logger.info(f"StreamRoom [{self.stream_id}] started.")
        

    def add_viewer(self,viewer_name:asyncio.Queue):
        self._msg_inbox.put_nowait(MsgJoin(viewer_name))

    def remove_viewer(self,viewer_name:asyncio.Queue):
        self._msg_inbox.put_nowait(MsgLeave(viewer_name))

    def broadcast(self,data:bytes):
        self._msg_inbox.put_nowait(MsgBroadcast(data))

    def stop(self):
        self._msg_inbox.put_nowait(MsgStop())


    async def _loop(self):
        try:
            while True:
                msg = await self._msg_inbox.get()


                if isinstance(msg, MsgBroadcast):
                        # Fan-out Logic
                        # We iterate directly over the set. No copy needed.
                        # Because we are inside the loop, we KNOW no one can add/remove
                        # a viewer right now. We have exclusive access.
                        for q in self.viewers:
                            if not q.full():
                                try:
                                    q.put_nowait(msg.data)
                                except asyncio.QueueFull:
                                    # Drop packet (Ghost Logic)
                                    pass
                elif isinstance(msg, MsgJoin):
                        self.viewers.add(msg.viewer_queue)
                        logger.info(f"[{self.stream_id}] Viewer joined. Count: {len(self.viewers)}")

                elif isinstance(msg, MsgLeave):
                        self.viewers.discard(msg.viewer_queue)
                        logger.info(f"[{self.stream_id}] Viewer left. Count: {len(self.viewers)}")

                elif isinstance(msg, MsgStop):
                        logger.info(f"[{self.stream_id}] Stopping...")
                        break
        except asyncio.CancelledError:
            logger.warning(f"[{self.stream_id}] Force killed.")
        finally:
            # Cleanup: Close all viewer queues so they don't hang
            for q in self.viewers:
                # Optional: Send a 'Stream Ended' signal to viewers before closing
                try:
                    # Create a "Stream Ended" message (you can customize this as needed)
                    stream_ended_message = b"STREAM_ENDED"
                    q.put_nowait(stream_ended_message)
                except asyncio.QueueFull:
                    # If the queue is full, we can log it or ignore it
                    logger.warning(f"[{self.stream_id}] Could not send stream ended signal to viewer queue")
            self.viewers.clear()

            

   

@dataclass
class RelayManager:
    rooms:Dict[str, StreamRoomActor]=field(default_factory=dict)

    def create_stream(self, stream_id: str) -> bool:
        if stream_id in self.rooms:
            return False # Stream already exists
        self.rooms[stream_id] = StreamRoomActor(stream_id)
        logger.info(f"Stream Created: {stream_id}")
        return True

    def delete_stream(self, stream_id: str):
        room = self.rooms.pop(stream_id, None)
        if room:
            room.stop()
            logger.info(f"Stream Deleted: {stream_id}")

    def get_room(self, stream_id: str) -> StreamRoomActor:
        return self.rooms.get(stream_id)
 