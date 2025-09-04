import socket
import threading
import json
import serial
import time

class SerialServer:

    global unlock_send_prefix, unlock_send_suffix
    global unlock_receive_prefix, unlock_receive_suffix
    global lock_status_send_prefix, lock_status_send_suffix
    global lock_status_receive_prefix, lock_status_receive_suffix
    global MaxBoard1

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
    def LockerIDtoStationlockNo(lockerId):
        if lockerId <= MaxBoard1:
            station = '01'
            lockNo = SerialServer.decimalToHexString(lockerId)
        else:
            station = '02'
            lockNo = SerialServer.decimalToHexString(lockerId - MaxBoard1)
        
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

    MaxBoard1 = 44

    def __init__(self, host='localhost', port=65432):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = {}
        self.channels = {
            #"rs232": None
            "rs485": None,
        }
        self.is_running = True

    def _setup_serial_ports(self):
        """Initializes and opens serial ports."""
        """
        try:
            # Configure and open RS232 port
            self.channels["rs232"] = serial.Serial('COM8', 9600, timeout=1)  # Change 'COM3' to your RS232 port
            print(f"RS232 port on {self.channels['rs232'].name} is ready.")
        except serial.SerialException as e:
            print(f"Failed to open RS232 port: {e}")
            self.channels["rs232"] = None
        """    

        try:
            # Configure and open RS485 port
            self.channels["rs485"] = serial.Serial('COM3', 9600, timeout=1)  # Change 'COM4' to your RS485 port
            print(f"RS485 port on {self.channels['rs485'].name} is ready.")
        except serial.SerialException as e:
            print(f"Failed to open RS485 port: {e}")
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
                        hex_message = unlock_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID) + unlock_send_suffix 
                    if action == "status":
                        hex_message = lock_status_send_prefix + SerialServer.LockerIDtoStationlockNo(lockerID) + lock_status_send_suffix
                     

                    
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
                time.sleep(1.9)  # Give the device time to respond
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
        """Starts the server and listens for connections."""
        self._setup_serial_ports()
        
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

