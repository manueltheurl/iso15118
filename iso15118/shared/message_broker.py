"""
Message broker for publishing ISO 15118 messages to external monitoring scripts.
Uses ZeroMQ for lightweight inter-process communication.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False
    logger.warning("ZeroMQ not available. Message broadcasting disabled. Install with: pip install pyzmq")


class MessageBroker:
    """
    Publishes decoded ISO 15118 messages to external subscribers via ZeroMQ.
    """
    
    def __init__(self, port: int = 5555, enabled: bool = True):
        self.port = port
        self.enabled = enabled and ZMQ_AVAILABLE
        self.context = None
        self.socket = None
        
        logger.debug(f"MessageBroker.__init__: port={port}, enabled={enabled}, ZMQ_AVAILABLE={ZMQ_AVAILABLE}")
        
        if self.enabled:
            try:
                self.context = zmq.Context()
                self.socket = self.context.socket(zmq.PUB)
                self.socket.bind(f"tcp://127.0.0.1:{self.port}")
                logger.info(f"Message broker started on tcp://127.0.0.1:{self.port}")
            except Exception as e:
                logger.error(f"Failed to start message broker: {e}")
                self.enabled = False
        else:
            logger.debug(f"Message broker disabled (enabled={enabled}, ZMQ_AVAILABLE={ZMQ_AVAILABLE})")
    
    def publish(self, message_type: str, namespace: str, decoded_message: Dict[str, Any]):
        """
        Publish a decoded message to all subscribers.
        
        Args:
            message_type: Type of message (e.g., "ChargeParameterDiscoveryRes")
            namespace: XML namespace of the message
            decoded_message: The decoded message as a dictionary
        """
        if not self.enabled or not self.socket:
            logger.debug(f"Skipping publish of {message_type} (broker disabled or no socket)")
            return
        
        try:
            payload = {
                "message_type": message_type,
                "namespace": namespace,
                "data": decoded_message,
            }
            
            # Send as topic-based message: "MESSAGE_TYPE json_payload"
            topic = message_type.replace(".", "_")  # Avoid dots in topics
            message = f"{topic} {json.dumps(payload)}"
            self.socket.send_string(message)
            logger.debug(f"Published message: {message_type}")
        except Exception as e:
            logger.error(f"Failed to publish message {message_type}: {e}")
    
    def close(self):
        """Close the broker connection."""
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
        logger.info("Message broker closed")


# Global broker instance
_broker: Optional[MessageBroker] = None


def get_message_broker(port: int = 5555, enabled: bool = True) -> MessageBroker:
    """Get or create the global message broker instance."""
    global _broker
    if _broker is None:
        _broker = MessageBroker(port=port, enabled=enabled)
    return _broker


def publish_message(message_type: str, namespace: str, decoded_message: Dict[str, Any]):
    """Convenience function to publish a message using the global broker."""
    broker = get_message_broker()
    broker.publish(message_type, namespace, decoded_message)
