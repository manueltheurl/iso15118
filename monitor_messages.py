#!/usr/bin/env python3
"""
ISO 15118 Message Monitor

This script subscribes to ISO 15118 messages published by the EVCC/SECC
and allows you to register callbacks for specific message types.

Example: Monitor ChargeParameterDiscoveryRes and extract EVSEMaxCurrent

Requirements:
    pip install pyzmq

Usage:
    python monitor_messages.py
"""

import json
import logging
import sys
from typing import Any, Callable, Dict

try:
    import zmq
except ImportError:
    print("ERROR: ZeroMQ not installed. Please install with: pip install pyzmq")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(asctime)s - %(name)s (%(lineno)d): %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class MessageMonitor:
    """
    Subscribes to ISO 15118 messages and dispatches them to registered callbacks.
    """

    def __init__(self, broker_port: int = 5555):
        self.broker_port = broker_port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.callbacks: Dict[str, list[Callable]] = {}

    def register_callback(self, message_type: str, callback: Callable):
        """
        Register a callback for a specific message type.

        Args:
            message_type: The message type to listen for (e.g., "ChargeParameterDiscoveryRes")
            callback: Function to call when message is received. 
                     Signature: callback(message_type: str, namespace: str, data: dict)
        """
        if message_type not in self.callbacks:
            self.callbacks[message_type] = []
        self.callbacks[message_type].append(callback)
        logger.info(f"Registered callback for message type: {message_type}")

    def connect(self):
        """Connect to the message broker."""
        try:
            self.socket.connect(f"tcp://127.0.0.1:{self.broker_port}")
            # Subscribe to all messages (empty string = all topics)
            self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
            logger.info(f"Connected to message broker on tcp://127.0.0.1:{self.broker_port}")
        except Exception as e:
            logger.error(f"Failed to connect to broker: {e}")
            raise

    def start(self):
        """Start listening for messages."""
        logger.info("Starting message monitor... (Press Ctrl+C to stop)")
        try:
            while True:
                # Receive message: "TOPIC json_payload"
                message_str = self.socket.recv_string()
                
                # Parse topic and payload
                parts = message_str.split(" ", 1)
                if len(parts) != 2:
                    logger.warning(f"Invalid message format: {message_str}")
                    continue
                
                topic, payload_json = parts
                
                try:
                    payload = json.loads(payload_json)
                    message_type = payload.get("message_type")
                    namespace = payload.get("namespace")
                    data = payload.get("data")
                    
                    # Dispatch to registered callbacks
                    if message_type in self.callbacks:
                        for callback in self.callbacks[message_type]:
                            try:
                                callback(message_type, namespace, data)
                            except Exception as e:
                                logger.error(f"Error in callback for {message_type}: {e}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON payload: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Stopping message monitor...")
        finally:
            self.socket.close()
            self.context.term()


# ===========================
# Example Callback Handlers
# ===========================

def handle_charge_parameter_discovery_res(message_type: str, namespace: str, data: Dict[str, Any]):
    """
    Callback for ChargeParameterDiscoveryRes messages.
    Extracts and prints EVSEMaxCurrent value.
    """
    try:
        # Navigate the message structure
        v2g_message = data.get("V2G_Message", {})
        body = v2g_message.get("Body", {})
        charge_params_res = body.get("ChargeParameterDiscoveryRes", {})
        
        # Extract AC EVSE parameters
        ac_evse_params = charge_params_res.get("AC_EVSEChargeParameter", {})
        evse_max_current = ac_evse_params.get("EVSEMaxCurrent", {})
        
        if evse_max_current:
            multiplier = evse_max_current.get("Multiplier", 0)
            unit = evse_max_current.get("Unit", "")
            value = evse_max_current.get("Value", 0)
            
            # Calculate actual value: value * 10^multiplier
            actual_value = value * (10 ** multiplier)
            
            print(f"\n{'='*70}")
            print(f"📊 ChargeParameterDiscoveryRes Received!")
            print(f"{'='*70}")
            print(f"  EVSEMaxCurrent: {actual_value} {unit}")
            print(f"    - Raw Value: {value}")
            print(f"    - Multiplier: {multiplier}")
            print(f"    - Unit: {unit}")
            print(f"{'='*70}\n")
            
        # Also extract other useful info
        response_code = charge_params_res.get("ResponseCode")
        evse_processing = charge_params_res.get("EVSEProcessing")
        
        logger.info(f"ResponseCode: {response_code}, EVSEProcessing: {evse_processing}")
        
    except Exception as e:
        logger.error(f"Error parsing ChargeParameterDiscoveryRes: {e}")


def handle_any_message(message_type: str, namespace: str, data: Dict[str, Any]):
    """
    Generic callback that logs all received messages.
    """
    logger.info(f"Received message: {message_type} (namespace: {namespace})")


# ===========================
# Main
# ===========================

def main():
    # Create monitor instance
    monitor = MessageMonitor(broker_port=5555)
    
    # Register callbacks for specific message types
    monitor.register_callback("ChargeParameterDiscoveryRes", handle_charge_parameter_discovery_res)
    
    # Optionally register a generic handler for all messages
    # Uncomment to log all message types:
    # for msg_type in ["SessionSetupRes", "ServiceDiscoveryRes", "PowerDeliveryRes", ...]:
    #     monitor.register_callback(msg_type, handle_any_message)
    
    # Connect and start monitoring
    try:
        monitor.connect()
        monitor.start()
    except Exception as e:
        logger.error(f"Monitor failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
