# server.py
# INI ADALAH KODE SERVER DARI JAWABAN SEBELUMNYA YANG SUDAH MEMILIKI LOGGING DETAIL
# PASTIKAN ANDA MENANGKAP OUTPUT LOG SETELAH "[SERVER LOG] Evaluating inputs for..."
import socket
import threading
import time
import random
from stratagems import STRATAGEM_LIST, get_stratagem_time_limit

HOST = '127.0.0.1'
PORT = 65432
MIN_PLAYERS = 2
TARGET_DEPLOYMENTS_TO_WIN = 5

class StratagemServer:
    def __init__(self):
        self.clients = {}
        self.player_inputs = {}
        self.current_stratagem = None
        self.current_time_limit = 0
        self.game_active = False
        self.round_start_time = 0
        self.lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.round_timer = None
        self.game_over_flag = False
        self.successful_deployments = 0
        self.target_deployments_to_win = TARGET_DEPLOYMENTS_TO_WIN
        self.timeout_has_fired_for_current_attempt = False
        self.submissions_processed_for_current_attempt = False

    def _broadcast_nolock(self, message, exclude_conn=None):
        active_connections = list(self.clients.keys())
        # print(f"[SERVER BROADCAST DEBUG] Broadcasting to {len(active_connections)} clients: {message}")
        for conn in active_connections:
            if conn == exclude_conn:
                continue
            try:
                conn.sendall(message.encode('utf-8'))
            except (socket.error, BrokenPipeError) as e:
                print(f"[SERVER ERROR] Error broadcasting: {e}. Client might be removed.")

    def broadcast(self, message, exclude_conn=None):
        with self.lock:
            self._broadcast_nolock(message, exclude_conn)

    def _remove_client(self, conn_to_remove):
        player_name_to_remove = None
        client_details = self.clients.pop(conn_to_remove, None)
        if client_details: player_name_to_remove = client_details.get('name')
        if player_name_to_remove and player_name_to_remove in self.player_inputs:
            del self.player_inputs[player_name_to_remove]
        print(f"[SERVER LOG] Player {player_name_to_remove or 'unknown'} disconnected/removed.")
        if self.game_active and len(self.clients) < MIN_PLAYERS:
            print("[SERVER LOG] Not enough players. Ending game.")
            self._broadcast_nolock("GAME_END Not enough players.")
            self.game_active = False; self.game_over_flag = True
            if self.round_timer: self.round_timer.cancel()

    def handle_client(self, conn, addr):
        player_name = None
        try:
            name_msg = conn.recv(1024).decode('utf-8')
            if name_msg.startswith("NAME:"):
                player_name = name_msg.split(":", 1)[1]
                with self.lock:
                    self.clients[conn] = {"name": player_name, "addr": addr}
                    self.player_inputs[player_name] = None
                print(f"[SERVER LOG] Player {player_name} from {addr} connected.")
                self.broadcast(f"MSG Player {player_name} has joined!")
                should_start, game_prog_info = False, None
                with self.lock:
                    if not self.game_active and len(self.clients) >= MIN_PLAYERS: should_start = True
                    elif self.game_active and self.current_stratagem:
                        seq_str = "".join(self.current_stratagem['sequence_keys'])
                        game_prog_info = f"STRATAGEM_INFO {self.current_stratagem['name']}|{self.current_stratagem['display']}|{seq_str}|{self.current_time_limit}"
                if should_start: self.start_game_sequence()
                elif game_prog_info: conn.sendall(f"MSG Game in progress. Current info:\n{game_prog_info}".encode('utf-8'))
            while not self.game_over_flag:
                data = conn.recv(1024).decode('utf-8')
                if not data: break
                if data.startswith("INPUT:") and self.game_active:
                    self.process_player_input(player_name, data.split(":", 1)[1])
        except ConnectionResetError: print(f"[SERVER WARNING] Connection reset: {player_name or addr}.")
        except Exception as e: print(f"[SERVER ERROR] Client {player_name or addr}: {e}"); import traceback; traceback.print_exc()
        finally:
            print(f"[SERVER LOG] Cleaning up client {player_name or addr}.")
            with self.lock: self._remove_client(conn)
            try: conn.close()
            except: pass

    def start_game_sequence(self):
        with self.lock:
            if self.game_active: return
            print("[SERVER LOG] Minimum players reached. Initializing game sequence...")
            self.game_active = True; self.successful_deployments = 0; self.game_over_flag = False
        self.pick_new_random_stratagem(initial_call=True)

    def pick_new_random_stratagem(self, outcome_previous_round=None, initial_call=False):
        print(f"[SERVER DEBUG] pick_new_random_stratagem START. Outcome prev: {outcome_previous_round}, Initial: {initial_call}")
        with self.lock:
            print(f"[SERVER DEBUG] pick_new_random_stratagem lock acquired. Game active: {self.game_active}")
            if not self.game_active: print("[SERVER LOG] pick_new_random_stratagem: Game not active, returning."); return
            if outcome_previous_round == "SUCCESS":
                self.successful_deployments += 1
                print(f"[SERVER LOG] Successful deployments: {self.successful_deployments}/{self.target_deployments_to_win}")
                if self.successful_deployments >= self.target_deployments_to_win:
                    print("[SERVER LOG] Target deployments reached! Mission accomplished!")
                    self._broadcast_nolock(f"GAME_OVER Mission accomplished: {self.successful_deployments} deployments!"); self.game_active = False; self.game_over_flag = True; return
            if not STRATAGEM_LIST: print("[SERVER CRITICAL ERROR] STRATAGEM_LIST empty!"); self._broadcast_nolock("GAME_END Server error: No Stratagems."); self.game_active = False; self.game_over_flag = True; return
            
            new_strat = random.choice(STRATAGEM_LIST)
            if hasattr(self, 'current_stratagem') and self.current_stratagem and len(STRATAGEM_LIST) > 1:
                while new_strat['name'] == self.current_stratagem['name']: new_strat = random.choice(STRATAGEM_LIST)
            self.current_stratagem = new_strat
            self.current_time_limit = get_stratagem_time_limit(self.current_stratagem['sequence_keys'])
            self.round_start_time = time.time()
            for p_name in list(self.player_inputs.keys()): self.player_inputs[p_name] = None
            
            self.timeout_has_fired_for_current_attempt = False
            self.submissions_processed_for_current_attempt = False
            seq_str = "".join(self.current_stratagem['sequence_keys'])
            msg = f"STRATAGEM_INFO {self.current_stratagem['name']}|{self.current_stratagem['display']}|{seq_str}|{self.current_time_limit}"
            log_prefix = "First" if initial_call else ("Next (after SUCCESS)" if outcome_previous_round == "SUCCESS" else "New (after FAIL)")
            print(f"[SERVER LOG] {log_prefix} Stratagem: {self.current_stratagem['name']} ({seq_str}). Time: {self.current_time_limit}s. Broadcasting.") # LOG KRUSIAL
            self._broadcast_nolock(msg) # BROADCAST KRUSIAL
            if self.round_timer: self.round_timer.cancel()
            self.round_timer = threading.Timer(self.current_time_limit, self.handle_timeout); self.round_timer.daemon = True; self.round_timer.start()
            print(f"[SERVER DEBUG] New round timer started for {self.current_stratagem['name']}.")
        print(f"[SERVER DEBUG] pick_new_random_stratagem END.")


    def process_player_input(self, player_name, sequence):
        with self.lock:
            strat_name = self.current_stratagem['name'] if self.current_stratagem else "N/A"
            # Log ini sudah ada di screenshot Anda:
            print(f"[SERVER DETAIL LOG] process_player_input: {player_name} for {strat_name}. Seq: {sequence}. Inputs: {self.player_inputs}")
            if not self.game_active or not self.current_stratagem or self.player_inputs.get(player_name) is not None: return
            self.player_inputs[player_name] = sequence
            all_submitted = True
            active_players = [p['name'] for p in self.clients.values()]
            if not active_players: print("[SERVER WARNING] No active players during process_player_input."); return
            for p_n in active_players:
                if self.player_inputs.get(p_n) is None: all_submitted = False; break
            if all_submitted:
                # Log ini sudah ada di screenshot Anda:
                print(f"[SERVER LOG] All players ({active_players}) submitted for {strat_name}.") 
                if self.timeout_has_fired_for_current_attempt: print(f"[SERVER LOG] Submissions for {strat_name} but timeout already processed.")
                else:
                    if self.round_timer: self.round_timer.cancel()
                    self.submissions_processed_for_current_attempt = True
                    # Log ini sudah ada di screenshot Anda:
                    print(f"[SERVER LOG] Evaluating inputs for {strat_name} (submissions complete).") 
                    self.evaluate_inputs()

    def handle_timeout(self):
        with self.lock:
            if not self.game_active or not self.current_stratagem: return
            strat_name = self.current_stratagem['name']
            print(f"[SERVER DEBUG] handle_timeout triggered for {strat_name}. Submissions processed: {self.submissions_processed_for_current_attempt}")
            if self.submissions_processed_for_current_attempt: print(f"[SERVER LOG] Timeout for {strat_name}, but submissions already processed. Ignoring."); return
            self.timeout_has_fired_for_current_attempt = True
            print(f"[SERVER LOG] Timeout for Stratagem: {strat_name}. Player inputs at timeout: {self.player_inputs}")
            all_inputs_present = True; active_players = [p['name'] for p in self.clients.values()]
            if not active_players and self.game_active: print("[SERVER LOG] No active players in timeout."); self.game_active=False; self.game_over_flag=True; return
            for p_n in active_players:
                if self.player_inputs.get(p_n) is None: all_inputs_present = False; break
            if all_inputs_present and active_players:
                print(f"[SERVER LOG] handle_timeout: Inputs for {strat_name} found present. Evaluating."); self.evaluate_inputs()
            else:
                print(f"[SERVER LOG] Timeout for {strat_name} is valid (missing inputs). Assigning new random stratagem.")
                self._broadcast_nolock(f"ROUND_FAIL Timeout! {strat_name} failed. New Stratagem incoming.")
                print(f"[SERVER CRITICAL DEBUG] BEFORE pick_new_random_stratagem from handle_timeout for {strat_name}")
                self.pick_new_random_stratagem(outcome_previous_round="FAIL")
                print(f"[SERVER CRITICAL DEBUG] AFTER pick_new_random_stratagem from handle_timeout for {strat_name}")

    def evaluate_inputs(self): # LOGGING DI SINI SANGAT PENTING DILIHAT
        with self.lock:
            if not self.game_active or not self.current_stratagem:
                print("[SERVER LOG] evaluate_inputs: Called when not active or no current stratagem."); return
            
            strat_name = self.current_stratagem['name']
            expected_seq = "".join(self.current_stratagem['sequence_keys'])
            # LOG KRUSIAL: Tampilkan input yang akan dievaluasi
            print(f"[SERVER EVAL LOG] Evaluating for {strat_name}. Expected: '{expected_seq}'. Actual Player Inputs: {self.player_inputs}") # LIHAT INI
            
            all_correct = True
            active_players = [p['name'] for p in self.clients.values()]
            if not active_players and self.game_active:
                print("[SERVER EVAL LOG] No active players, ending game."); self.game_active=False; self.game_over_flag=True; return

            if not active_players: 
                print("[SERVER EVAL LOG] No active players to evaluate."); all_correct = False

            for p_name_val in active_players: # Loop ini akan berjalan jika active_players tidak kosong
                player_actual_input = self.player_inputs.get(p_name_val)
                print(f"[SERVER EVAL DETAIL] Checking Player {p_name_val}: Input '{player_actual_input}', Expected '{expected_seq}'") # LIHAT INI
                if player_actual_input is None: 
                    print(f"[SERVER EVAL LOG] Input for {p_name_val} is None for {strat_name}. Evaluation FAILED.") # LIHAT INI
                    all_correct = False; break 
                if player_actual_input != expected_seq:
                    print(f"[SERVER EVAL LOG] Incorrect input detail: {p_name_val} for {strat_name}. Got: {player_actual_input}") # LIHAT INI
                    all_correct = False; break
            
            # ---- Titik Keputusan dan Pemanggilan Stratagem Berikutnya ----
            if all_correct and active_players: 
                print(f"[SERVER EVAL LOG] RESULT: All players correct for {strat_name}.") # LIHAT INI
                self._broadcast_nolock(f"ROUND_SUCCESS Stratagem {strat_name} successful! Next assignment...")
                print(f"[SERVER DEBUG] evaluate_inputs calling pick_new_random_stratagem (SUCCESS) for {strat_name}") # LIHAT INI
                self.pick_new_random_stratagem(outcome_previous_round="SUCCESS")
                print(f"[SERVER DEBUG] evaluate_inputs returned from pick_new_random_stratagem (SUCCESS) for {strat_name}") # LIHAT INI
            else:
                print(f"[SERVER EVAL LOG] RESULT: Input evaluation failed for {strat_name} (all_correct: {all_correct}, active_players: {len(active_players)}).") # LIHAT INI
                self._broadcast_nolock(f"ROUND_FAIL Input incorrect/incomplete for {strat_name}! New Stratagem incoming.")
                print(f"[SERVER DEBUG] evaluate_inputs calling pick_new_random_stratagem (FAIL) for {strat_name}") # LIHAT INI
                self.pick_new_random_stratagem(outcome_previous_round="FAIL")
                print(f"[SERVER DEBUG] evaluate_inputs returned from pick_new_random_stratagem (FAIL) for {strat_name}") # LIHAT INI

    def run(self): # (Sama seperti sebelumnya)
        self.server_socket.listen(MIN_PLAYERS + 3) 
        print(f"Server listening on {HOST}:{PORT}")
        print(f"Waiting for at least {MIN_PLAYERS} players.")
        print(f"Game win after {self.target_deployments_to_win} successful deployments.")
        try:
            while not self.game_over_flag :
                with self.lock: can_accept = len(self.clients) < (MIN_PLAYERS + 3)
                if can_accept : 
                    try:
                        self.server_socket.settimeout(1.0) 
                        conn, addr = self.server_socket.accept(); conn.settimeout(None) 
                        threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                    except socket.timeout: continue 
                    except OSError as e: 
                        if self.game_over_flag: break
                        else: print(f"[SERVER ERROR] Socket error: {e}"); raise e 
                else: time.sleep(0.1) 
        except KeyboardInterrupt: print("\n[SERVER INFO] Shutdown by Ctrl+C...")
        finally:
            print("[SERVER INFO] Shutting down server...")
            self.game_over_flag = True 
            if self.round_timer: self.round_timer.cancel()
            with self.lock:
                conns = list(self.clients.keys())
                for c in conns:
                    try: c.sendall("GAME_END Server shutting down.".encode('utf-8')); c.close()
                    except: pass
                self.clients.clear()
            if self.server_socket: self.server_socket.close()
            print("[SERVER INFO] Server shutdown complete.")

if __name__ == "__main__":
    if not STRATAGEM_LIST: print("[SERVER FATAL] Stratagem list empty!")
    else: server = StratagemServer(); server.run()