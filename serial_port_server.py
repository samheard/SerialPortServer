import paho.mqtt.client as mqtt
import socket
import threading
import json
import serial
import time
import os

class SerialServer:
    # MQTT setup
    MQTT_BROKER = "localhost"
    MQTT_COMMAND_TOPIC = "dispensary/command"
    MQTT_STATUS_TOPIC = "dispensary/status"

    def start_mqtt_service(self):
        def on_connect(mqttc, userdata, flags, rc):
            print("[MQTT] Connected to broker.")
            mqttc.subscribe(self.MQTT_COMMAND_TOPIC)
            mqttc.subscribe("door/command")  # Subscribe to door commands
            # Publish Home Assistant discovery for door
            self._publish_ha_discovery(mqttc)

        def on_message(mqttc, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
                
                # Check if this is a door command
                if msg.topic == "door/command":
                    self._handle_door_command(mqttc, payload)
                else:
                    # Handle dispensary commands
                    self._handle_dispensary_command(mqttc, payload)
                    
            except Exception as e:
                error = {"status": "error", "reason": str(e)}
                # Include command_id and locker_id in error response if available
                try:
                    payload = json.loads(msg.payload.decode('utf-8'))
                    command_id = payload.get("command_id")
                    locker_id = payload.get("lockerID") or payload.get("locker_id")
                    if command_id:
                        error["command_id"] = command_id
                    if locker_id:
                        error["locker_id"] = locker_id
                except:
                    pass
                
                # Determine which status topic to use
                if msg.topic == "door/command":
                    mqttc.publish("door/status", json.dumps(error))
                else:
                    mqttc.publish(self.MQTT_STATUS_TOPIC, json.dumps(error))
                print(f"[MQTT] Error: {e}")

        mqttc = mqtt.Client()
        mqttc.on_connect = on_connect
        mqttc.on_message = on_message
        mqttc.connect(self.MQTT_BROKER, 1883)
        print("[MQTT] Locker Service started. Listening for commands...")
        mqttc.loop_forever()
    
    def _publish_ha_discovery(self, mqttc):
        """Publish Home Assistant MQTT Discovery for door lock"""
        # Door lock discovery
        lock_config = {
            "name": "Remote Consult Room Door",
            "unique_id": "remote_consult_door_lock",
            "command_topic": "door/command",
            "state_topic": "door/status", 
            "payload_lock": '{"command": "lock"}',
            "payload_unlock": '{"command": "open"}',
            "state_locked": "closed",
            "state_unlocked": "open",
            "device": {
                "identifiers": ["remote_consult_door"],
                "name": "Remote Consult Room Door Lock",
                "manufacturer": "Custom",
                "model": "Serial Locker"
            }
        }
        
        # Publish discovery message
        discovery_topic = "homeassistant/lock/remote_consult_door/config"
        mqttc.publish(discovery_topic, json.dumps(lock_config), retain=True)
        print(f"[MQTT] Published Home Assistant discovery for door lock")
        
        # Publish initial status
        mqttc.publish("door/status", '{"status": "closed"}', retain=True)
    
    def _handle_door_command(self, mqttc, payload):
        """Handle door-specific commands"""
        channel = payload.get("channel", "rs485")
        action = payload.get("action") or payload.get("command")
        command_id = payload.get("command_id")
        
        # Handle Home Assistant lock commands
        if action == "lock":
            action = "status"  # For now, just check status when "lock" is requested
        
        # Use the configured door locker ID
        lockerID = self.door_locker_id
        
        hex_message = None
        if action == "open":
            hex_message = unlock_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID, self.max_lockers, self.lockers_per_station, self.door_locker_id) + unlock_send_suffix
        elif action == "status":
            hex_message = lock_status_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID, self.max_lockers, self.lockers_per_station, self.door_locker_id) + lock_status_send_suffix
        
        if hex_message:
            response = self._send_to_serial(channel, hex_message)
            # Parse response for open/closed status
            if response.get("status") == "success" and action == "status":
                data = response.get("response", "")
                if data.startswith(lock_status_receive_prefix) and data.endswith(lock_status_receive_suffix):
                    status_code = data[8:10]
                    if status_code == "01":
                        response["status"] = "open"
                    elif status_code == "00":
                        response["status"] = "closed"
            elif response.get("status") == "success" and action == "open":
                data = response.get("response", "")
                if data.startswith(unlock_receive_prefix) and data.endswith(unlock_receive_suffix):
                    result_code = data[10:12]
                    if result_code == "01":
                        response["status"] = "open"
                    else:
                        response["status"] = "failed"
        else:
            response = {"status": "error", "reason": "Invalid message format"}
        
        # Include command_id in response for tracking
        if command_id:
            response["command_id"] = command_id
        response["door_id"] = lockerID  # Include door ID for tracking
        
        # Publish to both topics for Home Assistant compatibility
        mqttc.publish("door/status", json.dumps(response))
        # Also publish simple status for Home Assistant
        simple_status = response["status"] if response["status"] in ["open", "closed"] else "closed"
        mqttc.publish("door/status", simple_status, retain=True)
        
        print(f"[MQTT] Door command processed: {payload}, response: {response}")
    
    def _handle_dispensary_command(self, mqttc, payload):
        """Handle dispensary/locker commands"""
        # Handle both message formats
        channel = payload.get("channel", "rs485")  # Default to rs485 if not specified
        action = payload.get("action") or payload.get("command")  # Support both "action" and "command"
        lockerID = payload.get("lockerID") or payload.get("locker_id")  # Support both formats
        command_id = payload.get("command_id")  # Get command_id for response tracking
        hex_message = None
        if action == "open":
            hex_message = unlock_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID, self.max_lockers, self.lockers_per_station, self.door_locker_id) + unlock_send_suffix
        if action == "status":
            hex_message = lock_status_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID, self.max_lockers, self.lockers_per_station, self.door_locker_id) + lock_status_send_suffix
        if channel and hex_message:
            response = self._send_to_serial(channel, hex_message)
            # Parse response for open/closed status
            if response.get("status") == "success" and action == "status":
                data = response.get("response", "")
                if data.startswith(lock_status_receive_prefix) and data.endswith(lock_status_receive_suffix):
                    status_code = data[8:10]
                    if status_code == "01":
                        response["status"] = "open"
                    elif status_code == "00":
                        response["status"] = "closed"
            elif response.get("status") == "success" and action == "open":
                data = response.get("response", "")
                if data.startswith(unlock_receive_prefix) and data.endswith(unlock_receive_suffix):
                    result_code = data[10:12]
                    if result_code == "01":
                        response["status"] = "open"
                    else:
                        response["status"] = "failed"
        else:
            response = {"status": "error", "reason": "Invalid message format"}
        
        # Include command_id and locker_id in response for tracking
        if command_id:
            response["command_id"] = command_id
        if lockerID:
            response["locker_id"] = lockerID
            
        mqttc.publish(self.MQTT_STATUS_TOPIC, json.dumps(response))
        print(f"[MQTT] Processed: {payload}, response: {response}")

    global unlock_send_prefix, unlock_send_suffix
    global unlock_receive_prefix, unlock_receive_suffix
    global lock_status_send_prefix, lock_status_send_suffix
    global lock_status_receive_prefix, lock_status_receive_suffix
    global MaxLockers

    @staticmethod
    def decimalToHexString(number):
        hex_string_with_prefix = hex(number)
        hex_string_without_prefix = hex_string_with_prefix[2:]

        if len(hex_string_without_prefix) == 2:
            return hex_string_without_prefix
        else:
            return ("0" + hex_string_without_prefix)

    # Convert LockerID in Decimal  into (station no and Lock no) in Hexadecimal format
    # There are two boards ('stations') with 24 lockers each. The first board is '01' and the second board is '02'.
    # The first board has lockers 1-24 and the second board has lockers 25-44 (can be upto 48 ).

    @staticmethod
    def LockerIDtoStationlockNo(lockerId, max_lockers=44, lockers_per_station=24, door_locker_id=48):
        # Handle door locker - always goes to station 02
        if lockerId == door_locker_id:
            station = '02'
            lockNo = SerialServer.decimalToHexString(lockerId - lockers_per_station)  # 48 - 24 = 24 (hex 18)
        else:
            # Check if locker_id is within valid range
            if lockerId > max_lockers:
                raise ValueError(f"Locker ID {lockerId} exceeds maximum allowed ({max_lockers})")
            
            # Calculate station and locker position
            station_num = ((lockerId - 1) // lockers_per_station) + 1  # Station number as integer
            lockNo = SerialServer.decimalToHexString(lockerId - ((station_num - 1) * lockers_per_station))
            station = f"{station_num:02d}"  # Convert to string format only here
            print(f"LockerID: {lockerId}, Station: {station}, LockNo: {lockNo}")    
        return (station + lockNo)

   


    # unlock command send to the lockers has 4 parts . Prefix + station no+locker number+suffix

    unlock_send_prefix = "900605"
    unlock_send_suffix = "03"

    # unlock command receives the result from lockers has 5 parts . Prefix + station no+locker number+success(01)/failure(00) of the command + suffix

    unlock_receive_prefix = "900785"
    unlock_receive_suffix = "03"

    # lock current status command send to the lockers has 4 parts . Prefix + station no+locker number+suffix

    lock_status_send_prefix = "900612"
    lock_status_send_suffix = "03"

    # lock current status command reeived from lockers has 5 parts . Prefix + station no+status(01 is open/00 is closed)+locker number+suffix

    lock_status_receive_prefix = "900792"
    lock_status_receive_suffix = "03"

    MaxLockers = 44

    import os

    def _read_config(self, config_path="config.env"):
        """Reads config file and returns a dict of config values."""
        import os
        # Look for config file in the same directory as this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(script_dir, config_path)
        
        config = {}
        try:
            with open(config_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if "=" in line:
                            key, value = line.split("=", 1)
                            config[key.strip()] = value.strip()
            print(f"Config loaded from: {config_file}")
        except FileNotFoundError:
            print(f"Config file not found: {config_file}, using defaults")
            pass
        return config

    def __init__(self, host='localhost', port=65432):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = {}
        config = self._read_config("config.env")
        self.serial_channel = config.get('SERIAL_CHANNEL', 'rs232')  # 'rs232' or 'rs485'
        self.serial_port = config.get('SERIAL_PORT', '/dev/ttyS0')   # e.g. '/dev/ttyS0' or 'COM8'
        self.serial_baudrate = int(config.get('SERIAL_BAUDRATE', '9600'))
        self.door_locker_id = int(config.get('DOOR_LOCKER_ID', '48'))  # Door acts as locker 48
        self.max_lockers = int(config.get('MAX_LOCKERS', '44'))  # Maximum regular lockers
        self.lockers_per_station = int(config.get('LOCKERS_PER_STATION', '24'))  # Lockers per station/board
        self.channels = {
            "rs232": None,
            "rs485": None,
        }
        self.is_running = True

    def _setup_serial_ports(self):
        """Initializes and opens serial ports using environment variables."""
        print(f"Attempting to open {self.serial_channel} on {self.serial_port} at {self.serial_baudrate} baud")
        # Setup only the selected channel
        if self.serial_channel == "rs232":
            try:
                self.channels["rs232"] = serial.Serial(self.serial_port, self.serial_baudrate, timeout=1)
                print(f"RS232 port on {self.channels['rs232'].name} is ready.")
            except serial.SerialException as e:
                print(f"Failed to open RS232 port {self.serial_port}: {e}")
                self.channels["rs232"] = None
        elif self.serial_channel == "rs485":
            try:
                self.channels["rs485"] = serial.Serial(self.serial_port, self.serial_baudrate, timeout=1)
                print(f"RS485 port on {self.channels['rs485'].name} is ready.")
            except serial.SerialException as e:
                print(f"Failed to open RS485 port {self.serial_port}: {e}")
                self.channels["rs485"] = None

    def _handle_client(self, conn, addr):
        """Handles communication with a single client."""
        print(f"Connected by {addr}")
        try:
            while self.is_running:
                data = conn.recv(1024)
                if not data:
                    break
                
                try:
                    message = json.loads(data.decode('utf-8'))
                    channel_name = message.get("channel")
                    action = message.get("action")
                    lockerID = message.get("lockerID")
                    hex_message = None

                    if action == "open":
                        hex_message = unlock_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID, self.max_lockers, self.lockers_per_station, self.door_locker_id) + unlock_send_suffix 
                    if action == "status":
                        hex_message = lock_status_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID, self.max_lockers, self.lockers_per_station, self.door_locker_id) + lock_status_send_suffix
                     

                    
                    if channel_name and hex_message:
                        response = self._send_to_serial(channel_name, hex_message)
                        conn.sendall(json.dumps(response).encode('utf-8'))
                    else:
                        error_response = {"status": "error", "reason": "Invalid message format"}
                        conn.sendall(json.dumps(error_response).encode('utf-8'))
                except json.JSONDecodeError:
                    error_response = {"status": "error", "reason": "Invalid JSON"}
                    conn.sendall(json.dumps(error_response).encode('utf-8'))
        finally:
            print(f"Client {addr} disconnected.")
            conn.close()

    def _send_to_serial(self, channel_name, hex_message):
        """Sends a hex message to the specified serial port and waits for a response."""
        port = self.channels.get(channel_name)
        if port and port.is_open:
            try:
                # Convert hex string to bytes
                data_to_send = bytes.fromhex(hex_message)
                port.write(data_to_send)
                print(f"Sent to {channel_name}: {hex_message}")
                
                # Wait for and read the response
                time.sleep(0.3)  # Give the device time to respond
                response_data = port.read_all()
                
                if response_data:
                    return {"status": "success", "response": response_data.hex().upper()}
                else:
                    return {"status": "sent", "response": None, "reason": "No response received"}
            except serial.SerialException as e:
                return {"status": "failed", "reason": f"Serial port error: {e}"}
            except Exception as e:
                return {"status": "failed", "reason": f"General error: {e}"}
        else:
            return {"status": "unavailable", "reason": f"{channel_name} port is not open or not configured"}

    def run(self):
        """Starts the server and listens for TCP and MQTT connections."""
        self._setup_serial_ports()
        # Start MQTT service in a background thread
        mqtt_thread = threading.Thread(target=self.start_mqtt_service)
        mqtt_thread.daemon = True
        mqtt_thread.start()
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen()
            print(f"Server listening on {self.host}:{self.port}")
            while self.is_running:
                try:
                    conn, addr = self.server_socket.accept()
                    client_thread = threading.Thread(target=self._handle_client, args=(conn, addr))
                    client_thread.daemon = True
                    client_thread.start()
                except KeyboardInterrupt:
                    self.is_running = False
                    print("Server shutting down...")
                    break
        finally:
            self.server_socket.close()
            print("Server socket closed.")

if __name__ == "__main__":
    server = SerialServer()
    server.run()

    def check_the_lock_status(self, channel,lockerId):
        station_lockNo = SerialServer.LockerIDtoStationlockNo(lockerId)
        check_status_command = lock_status_send_prefix + station_lockNo + lock_status_send_suffix
        response = self.send_message(channel, check_status_command)
        if response["status"] == "success":
            data = response["response"]
            if data.startswith(lock_status_receive_prefix) and data.endswith(lock_status_receive_suffix):
                status = data[8:10]
                if status == "01":
                    print(f"Locker {lockerId} is OPEN.")
                elif status == "00":
                    print(f"Locker {lockerId} is CLOSED.") 
        return response
    
    def unlock_the_locker(self, channel,lockerId):
        station_lockNo = SerialServer.LockerIDtoStationlockNo(lockerId)
        unlock_command = unlock_send_prefix + station_lockNo + unlock_send_suffix
        response = self.send_message(channel, unlock_command)
        if response["status"] == "success":
            data = response["response"]
            if data.startswith(unlock_receive_prefix) and data.endswith(unlock_receive_suffix):
                result = data[10:12]
                if result == "01":
                    print(f"Locker {lockerId} UNLOCK command SUCCESSFUL.")
                #elif result == "00":
                else:
                    print(f"Locker {lockerId} UNLOCK command FAILED.") 
        return response

