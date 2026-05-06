import tkinter as tk
from tkinter import scrolledtext, messagebox
import socket
import threading

class ChatClient:
    def __init__(self, master:tk.Tk):
        self.master = master
        master.title("Chat Client")
        master.grid_columnconfigure(index=list(range(4)), weight=1)
        master.grid_rowconfigure(index=list(range(4)), weight=1)

        self.client_socket = None
        self.is_connected = False
        self.thread = None

        self.create_widgets()

    def create_widgets(self):
        # Connection frame
        conn_frame = tk.Frame(self.master)
        conn_frame.grid(row=0,column=0, columnspan=6, pady=10, padx=10, sticky="NWSE")
        
        conn_frame.grid_columnconfigure(index=list(range(6)), weight=1)
        conn_frame.grid_rowconfigure(index=0, weight=1)

        tk.Label(conn_frame, text="Server:").grid(row=0,column=0)
        self.ip_entry = tk.Entry(conn_frame)
        self.ip_entry.grid(row=0,column=1)

        tk.Label(conn_frame, text="Port:").grid(row=0,column=2)
        self.port_entry = tk.Entry(conn_frame)
        self.port_entry.grid(row=0,column=3)

        tk.Label(conn_frame, text="Name:").grid(row=0,column=4)
        self.name_entry = tk.Entry(conn_frame)
        self.name_entry.grid(row=0,column=5)

        self.connect_button = tk.Button(self.master, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=1,column=0, columnspan=5)

        # Message display
        self.text_widget = tk.Text(self.master, state=tk.DISABLED)
        self.text_widget.grid(row=2,column=0, columnspan=6, pady=10, padx=10, sticky="NWSE")

        # Message sending frame
        msg_frame = tk.Frame(self.master)
        msg_frame.grid(row=3,column=0, columnspan=6, pady= 10, padx=10, sticky="NWSE")
        
        msg_frame.grid_columnconfigure(index=[0], weight=1)
        msg_frame.grid_rowconfigure(index=0, weight=1)
        
        self.msg_entry = tk.Entry(msg_frame)
        self.msg_entry.grid(row=0,column=0, sticky="NWSE")
        # Bind Return key so pressing Enter sends the messag
        self.msg_entry.bind("<Return>", self.send_message_event)
        
        self.send_button = tk.Button(msg_frame, text="Send", command=self.send_message)
        self.send_button.grid(row=0,column=1, sticky="NWSE")
        # Disabled until connected to prevent attempts to send without a socket
        self.send_button.config(state=tk.DISABLED)

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        ip = self.ip_entry.get()
        port_str = self.port_entry.get()
        name = self.name_entry.get()

        if not ip or not port_str or not name:
            messagebox.showerror("Error", "All fields must be filled out.")
            return

        try:
            port = int(port_str)
            # Create a TCP socket and connect to the server address
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self.is_connected = True


            # Protocol: immediately send the user's name so server can identify the client
            self.client_socket.sendall(name.encode())
            
            # Start a background thread to receive messages without blocking the GUI
            self.thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.thread.start()
            
            # Ensure closing the window first disconnects cleanly
            self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.add_message_to_text(f"--- Connected to {ip}:{port} ---")


            # Changes the label on the “Connect” button to “Disconnect.”
            self.connect_button.config(text="Disconnect")
            # Enables the “Send” button so the user can actually send messages.
            self.send_button.config(state=tk.NORMAL)
            # Re-enables the message-typing Entry box so the user can type text.
            self.msg_entry.config(state=tk.NORMAL)

        except (socket.error, ValueError) as e:
            messagebox.showerror("Connection Error", f"Could not connect: {e}")
            self.is_connected = False
            if self.client_socket:
                self.client_socket.close()

    def disconnect(self):
        if self.is_connected:
            self.is_connected = False
            self.client_socket.close()
            self.connect_button.config(text="Connect")
            self.send_button.config(state=tk.DISABLED)
            self.msg_entry.config(state=tk.DISABLED)
            self.add_message_to_text("--- Disconnected ---")

    def receive_messages(self):
        while self.is_connected:
            try:
                # Up to 1024 bytes per read; decode from bytes to str
                msg = self.client_socket.recv(1024).decode()
                if msg:
                    self.add_message_to_text(msg)
                else:
                    self.disconnect()
                    break
            except (socket.error, OSError):
                self.disconnect()
                break

    def send_message_event(self, event):
        self.send_message()

    def send_message(self):
        if self.is_connected:
            msg = self.msg_entry.get()
            if msg:
                try:
                    # convert to bytes and send
                    self.client_socket.sendall(msg.encode())
                    # clear entry after sending
                    self.msg_entry.delete(0, tk.END)
                except (socket.error, OSError):
                    self.disconnect()

    def add_message_to_text(self, message):
        # enable programmatic edits, append line, lock again, auto scroll to newest
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, message + "\n")
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.yview(tk.END)

    def on_closing(self):
        if self.is_connected:
            self.disconnect()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()