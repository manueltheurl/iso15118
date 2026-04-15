# ISO 15118 Message Monitoring System

This system allows you to monitor ISO 15118 messages in real-time and register callbacks for specific message types.

## Architecture

The system uses ZeroMQ for inter-process communication:
- **Publisher**: The ISO 15118 EXI codec publishes decoded messages
- **Subscriber**: Your monitoring script receives and processes those messages

## Quick Start

### 1. Install Dependencies

```bash
pip install pyzmq
```

### 2. Run the EVCC

In one terminal, start the EVCC as usual:

```bash
make run-evcc
```

The message broker is enabled by default and will publish messages on port 5555.

### 3. Run the Monitor

In another terminal, run the monitoring script:

```bash
cd /home/atraxoo/Documents/Business/Projects/JAM/EnerHanceRepo/Software/iso15118
python monitor_messages.py
```

### 4. See the Callbacks in Action

When a `ChargeParameterDiscoveryRes` message is received, you'll see output like:

```
======================================================================
📊 ChargeParameterDiscoveryRes Received!
======================================================================
  EVSEMaxCurrent: 32 A
    - Raw Value: -32
    - Multiplier: 0
    - Unit: A
======================================================================
```

## Configuration

You can configure the message broker using environment variables or a `.env` file:

```bash
# Enable/disable message broker (default: True)
MESSAGE_BROKER_ENABLED=True

# Port for message broker (default: 5555)
MESSAGE_BROKER_PORT=5555
```

## Creating Custom Callbacks

Edit `monitor_messages.py` to add your own callback handlers:

```python
def my_custom_handler(message_type: str, namespace: str, data: Dict[str, Any]):
    """Handle any message type"""
    # Your custom logic here
    print(f"Received {message_type}")
    # Extract data from the message
    # ...

# Register your callback
monitor.register_callback("PowerDeliveryRes", my_custom_handler)
```

## Message Types

Common ISO 15118-2 message types you can monitor:
- `SessionSetupRes`
- `ServiceDiscoveryRes`
- `ServicePaymentSelectionRes`
- `ChargeParameterDiscoveryRes`
- `PowerDeliveryRes`
- `CurrentDemandRes`
- `CableCheckRes`
- `PreChargeRes`
- `WeldingDetectionRes`
- `SessionStopRes`

## Troubleshooting

### "ZeroMQ not installed" error

Install pyzmq:
```bash
pip install pyzmq
```

### "Failed to connect to broker" error

Make sure the EVCC is running first. The message broker only starts when the EVCC starts.

### No messages received

1. Check that `MESSAGE_BROKER_ENABLED=True` in your environment
2. Verify the port matches between publisher and subscriber
3. Check the EVCC logs for any errors in the message broker initialization

## Architecture Details

### Message Flow

```
EVCC/SECC → EXI Decoder → Message Broker (ZeroMQ PUB) → Monitor Script (ZeroMQ SUB) → Your Callbacks
```

### Message Format

Messages are published with the format: `TOPIC json_payload`

Where `json_payload` is:
```json
{
  "message_type": "ChargeParameterDiscoveryRes",
  "namespace": "urn:iso:15118:2:2013:MsgDef",
  "data": { ... }  // Full decoded message
}
```
