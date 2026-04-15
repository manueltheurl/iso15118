#!/usr/bin/env python3
"""
Simple example: Monitor ChargeParameterDiscoveryRes and print EVSEMaxCurrent

This is a minimal script that does exactly what you asked for:
- Monitors incoming messages
- Detects ChargeParameterDiscoveryRes
- Extracts and prints EVSEMaxCurrent

Run this alongside `make run-evcc` in a separate terminal.
"""

import json
import sys

try:
    import zmq
except ImportError:
    print("ERROR: Please install pyzmq first:")
    print("  pip install pyzmq")
    sys.exit(1)


def main():
    # Setup ZeroMQ subscriber
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages
    
    print("🔌 Monitoring ISO 15118 messages...")
    print("⏳ Waiting for ChargeParameterDiscoveryRes...\n")
    
    try:
        while True:
            # Receive message
            message_str = socket.recv_string()
            
            # Parse: "TOPIC json_payload"
            parts = message_str.split(" ", 1)
            if len(parts) != 2:
                continue
            
            topic, payload_json = parts
            payload = json.loads(payload_json)
            
            message_type = payload["message_type"]
            data = payload["data"]
            
            # Look for ChargeParameterDiscoveryRes
            if message_type == "ChargeParameterDiscoveryRes":
                # Extract EVSEMaxCurrent
                v2g = data.get("V2G_Message", {})
                body = v2g.get("Body", {})
                res = body.get("ChargeParameterDiscoveryRes", {})
                ac_params = res.get("AC_EVSEChargeParameter", {})
                evse_max_current = ac_params.get("EVSEMaxCurrent", {})
                
                if evse_max_current:
                    value = evse_max_current.get("Value", 0)
                    multiplier = evse_max_current.get("Multiplier", 0)
                    unit = evse_max_current.get("Unit", "")
                    actual_value = value * (10 ** multiplier)
                    
                    # Print the value (this appears alongside the normal EVCC output)
                    print(f"\n⚡ CALLBACK: EVSEMaxCurrent = {actual_value} {unit}\n")
                    
    except KeyboardInterrupt:
        print("\n👋 Stopped monitoring")
    finally:
        socket.close()
        context.term()


if __name__ == "__main__":
    main()
