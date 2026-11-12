import json
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class Broadcaster:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, message_type: str, data: Any):
        """Broadcast JSON message to all connected clients."""
        if not self.active_connections:
            return

        payload = json.dumps({"type": message_type, "data": data}, default=str)
        dead_connections = []

        for conn in self.active_connections:
            try:
                await conn.send_text(payload)
            except Exception:
                dead_connections.append(conn)

        for conn in dead_connections:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

broadcaster = Broadcaster()

