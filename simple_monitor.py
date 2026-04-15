#!/usr/bin/env python3
"""
ISO 15118 Monitor with Relay Control

Features:
- Monitors ChargeParameterDiscoveryRes and prints EVSEMaxCurrent
- Controls relay via GPIO pin 2 on Raspberry Pi
  - HIGH when PowerDeliveryRes arrives (charging starts)
  - LOW when SessionStopRes arrives (charging ends)

Run this alongside `make run-evcc` in a separate terminal.
"""

import json
import sys
import platform

try:
    import zmq
except ImportError:
    print("ERROR: Please install pyzmq first:")
    print("  pip install pyzmq")
    sys.exit(1)

# GPIO setup for Raspberry Pi
RELAIS_PIN = 2
gpio_available = False
GPIO = None

# Try to import GPIO library (only available on Raspberry Pi)
try:
    import RPi.GPIO as GPIO
    gpio_available = True
    GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
    GPIO.setup(RELAIS_PIN, GPIO.OUT)
    GPIO.output(RELAIS_PIN, GPIO.LOW)  # Start with relay OFF
    print(f"✅ GPIO initialized - Pin {RELAIS_PIN} ready for relay control")
except (ImportError, RuntimeError) as e:
    print(f"⚠️  GPIO not available (not on Raspberry Pi or no permissions)")
    print("   Relay control will be simulated in console output only")


def set_relay(state: bool):
    """
    Set relay state.
    
    Args:
        state: True for HIGH/ON, False for LOW/OFF
    """
    if gpio_available and GPIO:
        GPIO.output(RELAIS_PIN, GPIO.HIGH if state else GPIO.LOW)
        print(f"🔌 RELAY: Pin {RELAIS_PIN} set to {'HIGH (ON)' if state else 'LOW (OFF)'}")
    else:
        print(f"🔌 RELAY (simulated): Pin {RELAIS_PIN} would be {'HIGH (ON)' if state else 'LOW (OFF)'}")


def main():
    # Setup ZeroMQ subscriber
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages
    
    print(f"🔌 Monitoring ISO 15118 messages...")
    print(f"📍 Platform: {platform.system()} {platform.machine()}")
    print(f"⏳ Waiting for messages...\n")
    
    relay_state = False  # Track current relay state
    
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
            
            # Check for PowerDeliveryRes (charging starts)
            elif message_type == "PowerDeliveryRes":
                v2g = data.get("V2G_Message", {})
                body = v2g.get("Body", {})
                power_delivery_res = body.get("PowerDeliveryRes", {})
                response_code = power_delivery_res.get("ResponseCode", "")
                
                print(f"\n⚡ PowerDeliveryRes received! ResponseCode: {response_code}")
                
                # Set relay HIGH when PowerDeliveryRes arrives with OK status
                if response_code == "OK" and not relay_state:
                    relay_state = True
                    set_relay(True)
            
            # Turn off relay when session stops
            elif message_type == "SessionStopRes":
                print(f"\n🛑 SessionStopRes received - session ended")
                if relay_state:
                    relay_state = False
                    set_relay(False)
                    
    except KeyboardInterrupt:
        print("\n👋 Stopped monitoring")
    finally:
        # Clean up
        if relay_state:
            print("🔌 Turning relay OFF before exit...")
            set_relay(False)
        
        if gpio_available and GPIO:
            GPIO.cleanup()
            print("✅ GPIO cleanup completed")
        
        socket.close()
        context.term()


if __name__ == "__main__":
    main()

