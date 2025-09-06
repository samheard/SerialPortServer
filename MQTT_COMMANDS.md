# MQTT Locker Service Documentation

## MQTT Topics

- **locker/command** (subscribe)
  - Send a JSON command to open or check status of a locker.
- **locker/status** (publish)
  - Receives the server response for the command.

## Example Python Publish Scripts

### Open locker 10
```python
import paho.mqtt.client as mqtt
import json

mqttc = mqtt.Client()
mqttc.connect("localhost")

command = {
    "channel": "rs485",   # or "rs232"
    "action": "open",
    "lockerID": 10
}

mqttc.publish("locker/command", json.dumps(command))
print("Published open command for locker 10.")
mqttc.disconnect()
```

### Check status of locker 5
```python
import paho.mqtt.client as mqtt
import json

mqttc = mqtt.Client()
mqttc.connect("localhost")

command = {
    "channel": "rs485",   # or "rs232"
    "action": "status",
    "lockerID": 5
}

mqttc.publish("locker/command", json.dumps(command))
print("Published status command for locker 5.")
mqttc.disconnect()
```

## Supported Actions
- `open`: Unlocks the specified locker.
- `status`: Checks the status (open/closed) of the specified locker.

## Example Commands
- Open locker 10 on RS485:
  ```json
  { "channel": "rs485", "action": "open", "lockerID": 10 }
  ```
- Check status of locker 5 on RS232:
  ```json
  { "channel": "rs232", "action": "status", "lockerID": 5 }
  ```
