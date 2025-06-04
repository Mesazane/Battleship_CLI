# client.py
import socket
import threading
import time
import sys
import argparse
try:
    import keyboard
except ImportError:
    print("Module 'keyboard' not found. Please install with 'pip install keyboard'.")
    print("Manual input will be used (type sequence then Enter).")
    keyboard = None


HOST = '127.0.0.1'
PORT = 65432

class StratagemClient:
    def __init__(self, player_name):
        self.player_name = player_name
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.current_stratagem_name = None
        self.current_stratagem_display = None
        self.current_stratagem_sequence = []
        self.current_time_limit = 0
        self.input_active = False
        self.collected_input = []
        self.input_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.sent_current_attempt = False # Flag to prevent multiple sends for one attempt

    def connect(self):
        try:
            self.client_socket.connect((HOST, PORT))
            self.client_socket.sendall(f"NAME:{self.player_name}".encode('utf-8'))
            listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)
            listen_thread.start()
            print(f"Connected to server as {self.player_name}. Waiting for game to start...")
            self.main_loop()
        except ConnectionRefusedError: print(f"Connection refused for {self.player_name}. Is the server running?")
        except Exception as e: print(f"Error connecting for {self.player_name}: {e}")
        finally:
            self.stop_event.set()
            self.cleanup_keyboard()
            if hasattr(self.client_socket, '_closed') and not self.client_socket._closed:
                try: self.client_socket.close()
                except Exception: pass
            print(f"Disconnected from server: {self.player_name}")

    def listen_to_server(self):
        print(f"[{self.player_name} CLIENT DEBUG] listen_to_server loop starting...")
        while not self.stop_event.is_set():
            try:
                message = self.client_socket.recv(1024).decode('utf-8')
                if not message:
                    print(f"SERVER INFO ({self.player_name}): Server closed connection or sent empty message."); self.stop_event.set(); break
                
                current_raw_msg = f"[{self.player_name} RAW SERVER MSG] {message.strip()}"
                print(current_raw_msg); sys.stdout.flush()

                if message.startswith("STRATAGEM_INFO"):
                    print(f"[{self.player_name} CLIENT LOG] Processing STRATAGEM_INFO..."); sys.stdout.flush()
                    _, data = message.split(" ", 1)
                    try: name, display, seq_str, time_limit_str = data.split("|")
                    except ValueError: print(f"ERROR ({self.player_name}): Malformed STRATAGEM_INFO: {data}"); sys.stdout.flush(); continue
                    
                    with self.input_lock:
                        self.current_stratagem_name, self.current_stratagem_display = name, display
                        self.current_stratagem_sequence, self.current_time_limit = list(seq_str), int(time_limit_str)
                        self.collected_input, self.input_active, self.sent_current_attempt = [], True, False # Reset for new stratagem
                    
                    print(f"\n[{self.player_name}] " + "="*40)
                    print(f"[{self.player_name}] INCOMING STRATAGEM: {self.current_stratagem_name}\n   Sequence: {self.current_stratagem_display} Code: {' '.join(self.current_stratagem_sequence)} Time: {self.current_time_limit}s")
                    print(f"[{self.player_name}] Enter sequence (ENSURE THIS WINDOW IS FOCUSED):") # Focus reminder
                    print(f"[{self.player_name}] " + "="*40); sys.stdout.flush()
                    threading.Thread(target=self.display_timer, args=(self.current_time_limit, self.current_stratagem_name), daemon=True).start()

                elif message.startswith("ROUND_SUCCESS"): print(f"\n[{self.player_name}] SUCCESS: {message.split(' ', 1)[1]}"); sys.stdout.flush(); self.input_active = False
                elif message.startswith("ROUND_FAIL"): print(f"\n[{self.player_name}] FAIL: {message.split(' ', 1)[1]}"); sys.stdout.flush(); self.input_active = False
                elif message.startswith("GAME_OVER"): print(f"\n[{self.player_name}] GAME OVER: {message.split(' ', 1)[1]}"); self.stop_event.set(); sys.stdout.flush(); self.cleanup_keyboard()
                elif message.startswith("GAME_END"): print(f"\n[{self.player_name}] GAME ENDED: {message.split(' ', 1)[1]}"); self.stop_event.set(); sys.stdout.flush(); self.cleanup_keyboard()
                elif message.startswith("MSG"): print(f"\n[{self.player_name} SERVER INFO] {message.split(' ', 1)[1]}"); sys.stdout.flush()
            except socket.timeout: print(f"[{self.player_name} CLIENT WARNING] Socket timeout."); continue
            except ConnectionResetError: print(f"ERROR ({self.player_name}): Connection to server lost."); self.stop_event.set(); break
            except Exception as e: print(f"CRITICAL ERROR in listen_to_server ({self.player_name}): {e}."); import traceback; traceback.print_exc(); self.stop_event.set(); break
        print(f"[{self.player_name} CLIENT LOG] listen_to_server loop has ended."); self.cleanup_keyboard()

    def cleanup_keyboard(self):
        if keyboard:
            try: keyboard.unhook_all()
            except Exception: pass # Ignore errors if already unhooked or other issues

    def display_timer(self, duration, strat_name_at_start):
        for i in range(duration, -1, -1):
            with self.input_lock: current_input_status, current_name = self.input_active, self.current_stratagem_name
            if self.stop_event.is_set() or not current_input_status or current_name != strat_name_at_start: return
            sys.stdout.write(f"\r[{self.player_name}] Time left: {i}s... "); sys.stdout.flush()
            time.sleep(1)
        with self.input_lock: current_input_status, current_name = self.input_active, self.current_stratagem_name
        # Check if timer naturally expired for the current active stratagem attempt
        if current_input_status and not self.sent_current_attempt and current_name == strat_name_at_start:
            sys.stdout.write(f"\r[{self.player_name}] Time's up! Waiting for server response...\n"); sys.stdout.flush()
        else: # Timer interrupted or input was sent
            sys.stdout.write("\r \r"); sys.stdout.flush() # Clear the timer line

    def send_input_atomically(self):
        # This function is called from on_key_press_handler, which holds the input_lock
        if not self.input_active:
            print(f"\n[{self.player_name} CLIENT INFO] Send attempt ignored: input_active is False."); sys.stdout.flush(); return
        if self.sent_current_attempt:
            print(f"\n[{self.player_name} CLIENT INFO] Send attempt ignored: Already sent for this attempt."); sys.stdout.flush(); return
            
        input_str = "".join(self.collected_input)
        # Critical Log: Confirming send attempt
        print(f"\n[{self.player_name} CLIENT ACTION] Preparing to send: '{input_str}' (Input Active: {self.input_active}, Sent This Attempt: {self.sent_current_attempt})"); sys.stdout.flush()
        try:
            self.client_socket.sendall(f"INPUT:{input_str}".encode('utf-8'))
            print(f"[{self.player_name} CLIENT ACTION] Successfully sent: '{input_str}'"); sys.stdout.flush()
            self.sent_current_attempt = True # Mark as sent for this attempt
        except socket.error as e:
            print(f"ERROR ({self.player_name}) trying to send input: {e}"); sys.stdout.flush(); self.stop_event.set()

    def on_key_press_handler(self, event):
        # Critical Log: To see if key presses are being captured for the correct player
        if hasattr(event, 'name') and event.name: # Ensure event.name is not None
            print(f"[CLIENT INPUT DEBUG - {self.player_name}] Key Event: '{event.name.upper()}'. Input Active: {self.input_active}, Sent This Attempt: {self.sent_current_attempt}, Collected: {''.join(self.collected_input)}")
            sys.stdout.flush()
        
        with self.input_lock:
            if not self.input_active or self.sent_current_attempt or not self.current_stratagem_sequence or self.stop_event.is_set(): return
            if not hasattr(event, 'name') or event.name is None: return
            
            key = event.name.upper()
            if key in ['W', 'A', 'S', 'D']:
                if len(self.collected_input) < len(self.current_stratagem_sequence):
                    self.collected_input.append(key)
                    current_display_input = "".join(self.collected_input); target_length = len(self.current_stratagem_sequence)
                    progress_bar = f"[{'#'*len(self.collected_input)}{'-'*(target_length - len(self.collected_input))}]"
                    sys.stdout.write(f"\r[{self.player_name}] Input: {current_display_input.ljust(target_length)} {progress_bar} ({len(self.collected_input)}/{target_length})"); sys.stdout.flush()
                    
                    if len(self.collected_input) == len(self.current_stratagem_sequence):
                        sys.stdout.write("\n"); sys.stdout.flush() # Newline after completing sequence characters
                        self.send_input_atomically() # Send the completed input
    
    def manual_input_loop(self):
        print(f"\n[{self.player_name} MANUAL INPUT MODE]")
        while not self.stop_event.is_set():
            time.sleep(0.1); current_name, current_seq_list, is_active, already_sent = None, None, False, False
            with self.input_lock:
                if self.input_active and self.current_stratagem_name and self.current_stratagem_sequence:
                    current_name, current_seq_list, is_active, already_sent = self.current_stratagem_name, self.current_stratagem_sequence, True, self.sent_current_attempt
            if is_active and not already_sent:
                try:
                    prompt = f"[{self.player_name}] Enter for {current_name} ({''.join(current_seq_list)}): "
                    user_in = input(prompt).upper().strip()
                    with self.input_lock:
                        if self.input_active and not self.sent_current_attempt and self.current_stratagem_name == current_name: # Re-check conditions
                            self.collected_input = [c for c in user_in if c in ['W','A','S','D']][:len(current_seq_list)]
                            if len(self.collected_input) == len(current_seq_list): self.send_input_atomically()
                            else: print(f"Invalid. Need {len(current_seq_list)} WASD keys."); self.collected_input = []
                except Exception as e: print(f"ERROR ({self.player_name}) manual input: {e}"); self.stop_event.set(); break
            if self.stop_event.is_set(): break

    def main_loop(self):
        if keyboard:
            print(f"[{self.player_name}] Using direct WASD (ENSURE THIS WINDOW IS FOCUSED). suppress=True")
            try:
                keys_hooked = []
                for key_char in ['w','a','s','d']: # Hook lowercase keys
                    if hasattr(keyboard, 'on_press_key'): 
                        keyboard.on_press_key(key_char, self.on_key_press_handler, suppress=True) # suppress=True
                        keys_hooked.append(key_char.upper())
                    else: raise AttributeError("keyboard.on_press_key not found in keyboard module")
                print(f"[{self.player_name}] Keys {', '.join(keys_hooked)} successfully hooked.")
            except Exception as e:
                print(f"ERROR ({self.player_name}) hooking WASD keys: {e}. Falling back to manual input mode."); self.cleanup_keyboard(); self.manual_input_loop(); return
            
            while not self.stop_event.is_set(): time.sleep(0.2) # Keep main thread alive for keyboard hooks
            
            print(f"[{self.player_name} CLIENT LOG] Main loop ending due to stop_event set."); self.cleanup_keyboard()
        else: 
            print(f"[{self.player_name}] Keyboard module not available. Using manual input mode."); self.manual_input_loop()
        
        print(f"[{self.player_name} CLIENT LOG] Waiting for listener thread to complete session..."); 
        self.stop_event.wait(timeout=1) # Brief wait for listen_to_server to finish
        print(f"[{self.player_name} CLIENT LOG] Main_loop fully terminated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Helldivers Stratagem Minigame Client"); 
    parser.add_argument("--name",type=str,required=True,help="Your player name")
    args = parser.parse_args()
    
    client = StratagemClient(args.name)
    try: 
        client.connect()
    except KeyboardInterrupt: 
        print(f"\n[{args.name}] Client shutdown initiated by user (Ctrl+C).")
        if hasattr(client, 'stop_event'): client.stop_event.set() 
    finally: 
        print(f"[{args.name}] Client is finally shutting down.")