import socket
import json

class SerialClient:
    def __init__(self, host='localhost', port=65432):
        self.host = host
        self.port = port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
    def connect(self):
        """Establishes a connection to the server."""
        try:
            self.client_socket.connect((self.host, self.port))
            print("Connected to server.")
            return True
        except ConnectionRefusedError:
            print("Connection refused. Is the server running?")
            return False

    def send_message(self, channel, action, lockerID):
        """Sends a message to the server and returns the response."""
        message = {
            "channel": channel,
            "action": action,
            "lockerID": lockerID
        }
        try:
            self.client_socket.sendall(json.dumps(message).encode('utf-8'))
            response_data = self.client_socket.recv(1024)
            response = json.loads(response_data.decode('utf-8'))
            return response
        except (socket.error, json.JSONDecodeError) as e:
            print(f"Communication error: {e}")
            return {"status": "error", "reason": "Network or data parsing issue"}

    def close(self):
        """Closes the client connection."""
        self.client_socket.close()
        print("Connection closed.")
    

if __name__ == "__main__":
    client = SerialClient()
    if client.connect():
        
        # Example 1: Sending a message to the RS485 channel
        print("\nSending message to RS485 channel...")
        response = client.send_message("rs485", "open",  5)
        print("Server response:", response)
        response = client.send_message("rs485", "status",  5)
        print("Server response:", response)

        
        client.close()