# client.py
import socket
import threading
import time
import sys
import argparse
try:
    import keyboard
except ImportError:
    print("Modul 'keyboard' tidak ditemukan. Silakan install dengan 'pip install keyboard'.")
    print("Input manual akan digunakan (ketik urutan lalu Enter).")
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
        self.sent_current_attempt = False

    def connect(self):
        try:
            self.client_socket.connect((HOST, PORT))
            self.client_socket.sendall(f"NAME:{self.player_name}".encode('utf-8'))
            listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)
            listen_thread.start()
            print(f"Connected to server as {self.player_name}. Waiting for game to start...")
            self.main_loop()
        except ConnectionRefusedError: print(f"Connection refused for {self.player_name}.")
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
                    print(f"SERVER INFO ({self.player_name}): Server closed connection."); self.stop_event.set(); break
                
                # Selalu flush setelah print untuk memastikan output segera muncul
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
                        self.collected_input, self.input_active, self.sent_current_attempt = [], True, False
                    
                    print(f"\n[{self.player_name}] " + "="*40)
                    print(f"[{self.player_name}] INCOMING STRATAGEM: {self.current_stratagem_name}\n   Sequence: {self.current_stratagem_display} Code: {' '.join(self.current_stratagem_sequence)} Time: {self.current_time_limit}s")
                    print(f"[{self.player_name}] Enter sequence (ENSURE THIS WINDOW IS FOCUSED):") # Peringatan Fokus
                    print(f"[{self.player_name}] " + "="*40); sys.stdout.flush()
                    threading.Thread(target=self.display_timer, args=(self.current_time_limit, self.current_stratagem_name), daemon=True).start()

                elif message.startswith("ROUND_SUCCESS"): print(f"\n[{self.player_name}] SUCCESS: {message.split(' ', 1)[1]}"); sys.stdout.flush(); self.input_active = False
                elif message.startswith("ROUND_FAIL"): print(f"\n[{self.player_name}] FAIL: {message.split(' ', 1)[1]}"); sys.stdout.flush(); self.input_active = False
                elif message.startswith("GAME_OVER"): print(f"\n[{self.player_name}] GAME OVER: {message.split(' ', 1)[1]}"); self.stop_event.set(); sys.stdout.flush(); self.cleanup_keyboard()
                elif message.startswith("GAME_END"): print(f"\n[{self.player_name}] GAME ENDED: {message.split(' ', 1)[1]}"); self.stop_event.set(); sys.stdout.flush(); self.cleanup_keyboard()
                elif message.startswith("MSG"): print(f"\n[{self.player_name} SERVER INFO] {message.split(' ', 1)[1]}"); sys.stdout.flush()
            except socket.timeout: print(f"[{self.player_name} CLIENT WARNING] Socket timeout."); continue
            except ConnectionResetError: print(f"ERROR ({self.player_name}): Connection lost."); self.stop_event.set(); break
            except Exception as e: print(f"CRITICAL ERROR listen_to_server ({self.player_name}): {e}."); import traceback; traceback.print_exc(); self.stop_event.set(); break
        print(f"[{self.player_name} CLIENT LOG] listen_to_server loop ended."); self.cleanup_keyboard()

    def cleanup_keyboard(self):
        if keyboard:
            try: keyboard.unhook_all()
            except Exception: pass

    def display_timer(self, duration, strat_name_at_start):
        for i in range(duration, -1, -1):
            with self.input_lock: current_input_status, current_name = self.input_active, self.current_stratagem_name
            if self.stop_event.is_set() or not current_input_status or current_name != strat_name_at_start: return
            sys.stdout.write(f"\r[{self.player_name}] Time left: {i}s... "); sys.stdout.flush()
            time.sleep(1)
        with self.input_lock: current_input_status, current_name = self.input_active, self.current_stratagem_name
        if current_input_status and current_name == strat_name_at_start: sys.stdout.write(f"\r[{self.player_name}] Time's up! Waiting...\n"); sys.stdout.flush()
        else: sys.stdout.write("\r \r"); sys.stdout.flush()

    def send_input_atomically(self):
        with self.input_lock: 
            if not self.input_active: print(f"\n[{self.player_name} CLIENT INFO] Send attempt while input_active=False."); sys.stdout.flush(); return
            if self.sent_current_attempt: print(f"\n[{self.player_name} CLIENT INFO] Already sent for this attempt."); sys.stdout.flush(); return
            
            input_str = "".join(self.collected_input)
            # Log ini sangat penting untuk dilihat SEBELUM ROUND_FAIL muncul dari server
            print(f"\n[{self.player_name} CLIENT ACTION] Preparing to send: {input_str} (Input Active: {self.input_active}, Sent Attempt: {self.sent_current_attempt})"); sys.stdout.flush()
            try:
                self.client_socket.sendall(f"INPUT:{input_str}".encode('utf-8'))
                print(f"[{self.player_name} CLIENT ACTION] Successfully sent: {input_str}"); sys.stdout.flush()
                self.sent_current_attempt = True # Tandai sudah mengirim
            except socket.error as e: print(f"ERROR ({self.player_name}) sending input: {e}"); sys.stdout.flush(); self.stop_event.set()

    def on_key_press_handler(self, event):
        # Log ini untuk memastikan handler dipanggil untuk pemain yang benar
        print(f"[CLIENT INPUT DEBUG - {self.player_name}] Event: {event.name if hasattr(event, 'name') else 'UNKNOWN'}. Input Active: {self.input_active}, Sent: {self.sent_current_attempt}")
        sys.stdout.flush() # Langsung flush log ini
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
                        sys.stdout.write("\n"); sys.stdout.flush()
                        self.send_input_atomically()
    
    def manual_input_loop(self): # (Sama seperti sebelumnya)
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
                        if self.input_active and not self.sent_current_attempt and self.current_stratagem_name == current_name:
                            self.collected_input = [c for c in user_in if c in ['W','A','S','D']][:len(current_seq_list)]
                            if len(self.collected_input) == len(current_seq_list): self.send_input_atomically()
                            else: print(f"Invalid. Need {len(current_seq_list)} WASD keys."); self.collected_input = []
                except Exception as e: print(f"ERROR ({self.player_name}) manual input: {e}"); self.stop_event.set(); break
            if self.stop_event.is_set(): break

    def main_loop(self):
        if keyboard:
            # PENTING: suppress=True untuk menghindari ghost input. Pastikan FOKUS JENDELA BENAR.
            print(f"[{self.player_name}] Using direct WASD (ENSURE THIS WINDOW IS FOCUSED). suppress=True")
            try:
                keys_hooked = []
                for key_char in ['w','a','s','d']:
                    if hasattr(keyboard, 'on_press_key'): 
                        keyboard.on_press_key(key_char, self.on_key_press_handler, suppress=True) # suppress=True
                        keys_hooked.append(key_char.upper())
                    else: raise AttributeError("keyboard.on_press_key not found")
                print(f"[{self.player_name}] Keys {', '.join(keys_hooked)} hooked.")
            except Exception as e:
                print(f"ERROR ({self.player_name}) hooking keys: {e}. Fallback to manual."); self.cleanup_keyboard(); self.manual_input_loop(); return
            while not self.stop_event.is_set(): time.sleep(0.2)
            print(f"[{self.player_name} CLIENT LOG] Main loop ending."); self.cleanup_keyboard()
        else: print(f"[{self.player_name}] Keyboard module N/A. Manual input."); self.manual_input_loop()
        print(f"[{self.player_name} CLIENT LOG] Waiting for listener..."); self.stop_event.wait(timeout=1); print(f"[{self.player_name} CLIENT LOG] Main_loop terminated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stratagem Client"); parser.add_argument("--name",type=str,required=True,help="Player name"); args = parser.parse_args()
    client = StratagemClient(args.name)
    try: client.connect()
    except KeyboardInterrupt: print(f"\n[{args.name}] Shutdown by user."); client.stop_event.set()
    finally: print(f"[{args.name}] Client final shutdown.")