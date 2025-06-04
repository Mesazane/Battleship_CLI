# server.py
import socket
import threading
import time
import random
from stratagems import STRATAGEM_LIST, get_stratagem_time_limit

HOST = '127.0.0.1' # Loopback address for local machine
PORT = 65432       # Port to listen on (non-privileged ports are > 1023)
MIN_PLAYERS = 2
TARGET_DEPLOYMENTS_TO_WIN = 5 # Number of successful stratagems to win

class StratagemServer:
    def __init__(self):
        self.clients = {}  # Stores client_socket: {name, addr}
        self.player_inputs = {} # Stores player_name: submitted_sequence_string
        
        self.current_stratagem = None
        self.current_time_limit = 0
        
        self.game_active = False
        self.round_start_time = 0 # Tracks when the current stratagem input phase started
        self.lock = threading.Lock() # To protect shared resources
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow address reuse
        self.server_socket.bind((HOST, PORT))
        
        self.round_timer = None # threading.Timer object for current round
        self.game_over_flag = False # Set to True to signal server shutdown
        
        self.successful_deployments = 0 # Counter for winning condition

        # Flags for synchronizing player submissions and server timeout for the current attempt
        self.timeout_has_fired_for_current_attempt = False
        self.submissions_processed_for_current_attempt = False

    def _broadcast_nolock(self, message, exclude_conn=None):
        # This internal method assumes the caller already holds self.lock
        active_connections = list(self.clients.keys()) # Create a stable list for iteration
        # print(f"[SERVER BROADCAST DEBUG] Broadcasting to {len(active_connections)} clients: {message}") # Uncomment for verbose broadcast log
        for conn_socket in active_connections:
            if conn_socket == exclude_conn:
                continue
            try:
                conn_socket.sendall(message.encode('utf-8'))
            except (socket.error, BrokenPipeError) as e:
                # Log error; actual client removal is handled by handle_client on recv failure
                print(f"[SERVER ERROR] Error broadcasting to a client: {e}. Client might be removed by its handler.")

    def broadcast(self, message, exclude_conn=None):
        # Public method to broadcast messages; it acquires the lock.
        with self.lock:
            self._broadcast_nolock(message, exclude_conn)

    def _remove_client(self, conn_to_remove):
        # This internal method assumes the caller already holds self.lock
        player_name_to_remove = None
        client_details = self.clients.pop(conn_to_remove, None) # Remove client and get its details
        
        if client_details:
            player_name_to_remove = client_details.get('name')
        
        # Also remove any pending input from this player
        if player_name_to_remove and player_name_to_remove in self.player_inputs:
            del self.player_inputs[player_name_to_remove]
        
        print(f"[SERVER LOG] Player {player_name_to_remove or 'unknown'} disconnected or was removed.")

        # Check if game needs to end due to insufficient players
        if self.game_active and len(self.clients) < MIN_PLAYERS:
            print("[SERVER LOG] Not enough players to continue the mission. Ending game.")
            self._broadcast_nolock("GAME_END Not enough players to continue the mission.") # Use _nolock as lock is held
            self.game_active = False
            self.game_over_flag = True # Signal to potentially stop the server if desired, or just end current game
            if self.round_timer:
                self.round_timer.cancel()

    def handle_client(self, client_socket, client_address):
        player_name = None
        try:
            # Initial message from client should be their name
            name_msg = client_socket.recv(1024).decode('utf-8')
            if name_msg.startswith("NAME:"):
                player_name = name_msg.split(":", 1)[1]
                with self.lock:
                    self.clients[client_socket] = {"name": player_name, "addr": client_address}
                    self.player_inputs[player_name] = None # Initialize input state for this player
                
                print(f"[SERVER LOG] Player {player_name} from {client_address} connected.")
                self.broadcast(f"MSG Player {player_name} has joined the game!") # Public broadcast is fine here

                should_start_game_now = False
                game_already_in_progress_info = None

                with self.lock: # Check game state under lock
                    if not self.game_active and len(self.clients) >= MIN_PLAYERS:
                        should_start_game_now = True
                    elif self.game_active and self.current_stratagem: # If game started and a stratagem is active
                        # Send current stratagem info to late joiner
                        seq_str = "".join(self.current_stratagem['sequence_keys'])
                        game_already_in_progress_info = f"STRATAGEM_INFO {self.current_stratagem['name']}|{self.current_stratagem['display']}|{seq_str}|{self.current_time_limit}"
                
                if should_start_game_now:
                    self.start_game_sequence() # Will handle picking the first stratagem
                elif game_already_in_progress_info:
                    # Inform late joiner about game in progress and current stratagem
                    client_socket.sendall("MSG Game in progress. Current Stratagem info follows:\n".encode('utf-8'))
                    client_socket.sendall(game_already_in_progress_info.encode('utf-8'))

            # Main loop for receiving client inputs
            while not self.game_over_flag: # Loop until game over or client disconnects
                data = client_socket.recv(1024).decode('utf-8')
                if not data: # Empty data means client disconnected
                    print(f"[SERVER LOG] Player {player_name or client_address} sent empty data (disconnected).")
                    break 

                if data.startswith("INPUT:") and self.game_active:
                    sequence = data.split(":", 1)[1]
                    self.process_player_input(player_name, sequence)
                # Add other message handling if needed

        except ConnectionResetError:
            print(f"[SERVER WARNING] Connection reset by {player_name or client_address}.")
        except Exception as e:
            print(f"[SERVER ERROR] Error with client {player_name or client_address}: {e}")
            import traceback; traceback.print_exc()
        finally:
            print(f"[SERVER LOG] Cleaning up client {player_name or client_address}.")
            with self.lock: # Ensure lock is held when removing client
                self._remove_client(client_socket)
            try:
                client_socket.close()
            except socket.error as e_close:
                print(f"[SERVER ERROR] Error closing client socket for {player_name or client_address}: {e_close}")

    def start_game_sequence(self):
        with self.lock: # Ensure game starting logic is atomic
            if self.game_active: # Prevent starting if already active
                return
            print("[SERVER LOG] Minimum players reached. Initializing game sequence...")
            self.game_active = True
            self.successful_deployments = 0
            self.game_over_flag = False # Reset game over flag for a new game session
        
        self.pick_new_random_stratagem(initial_call=True)


    def pick_new_random_stratagem(self, outcome_previous_round=None, initial_call=False):
        # This function selects and broadcasts the next (or first) stratagem
        print(f"[SERVER DEBUG] pick_new_random_stratagem START. Outcome prev: {outcome_previous_round}, Initial: {initial_call}")
        with self.lock:
            print(f"[SERVER DEBUG] pick_new_random_stratagem lock acquired. Game active: {self.game_active}")
            if not self.game_active: 
                print("[SERVER LOG] pick_new_random_stratagem: Game not active, returning."); return

            if outcome_previous_round == "SUCCESS":
                self.successful_deployments += 1
                print(f"[SERVER LOG] Successful deployments: {self.successful_deployments}/{self.target_deployments_to_win}")
                if self.successful_deployments >= self.target_deployments_to_win:
                    print("[SERVER LOG] Target deployments reached! Mission accomplished!")
                    self._broadcast_nolock(f"GAME_OVER Mission accomplished with {self.successful_deployments} successful deployments! For Super Earth!")
                    self.game_active = False; self.game_over_flag = True; return

            if not STRATAGEM_LIST: 
                print("[SERVER CRITICAL ERROR] STRATAGEM_LIST is empty! Cannot pick new stratagem.")
                self._broadcast_nolock("GAME_END Server error: No Stratagems available."); self.game_active = False; self.game_over_flag = True; return
            
            new_selected_stratagem = random.choice(STRATAGEM_LIST)
            # Optional: Prevent immediate repetition of the exact same stratagem
            if hasattr(self, 'current_stratagem') and self.current_stratagem and len(STRATAGEM_LIST) > 1:
                while new_selected_stratagem['name'] == self.current_stratagem['name']:
                    new_selected_stratagem = random.choice(STRATAGEM_LIST)
            self.current_stratagem = new_selected_stratagem
            
            self.current_time_limit = get_stratagem_time_limit(self.current_stratagem['sequence_keys'])
            self.round_start_time = time.time()
            
            # Reset player inputs for the new stratagem/attempt
            # Iterate over a copy of keys if modifying dict, but here just setting values
            for p_name_key in list(self.player_inputs.keys()): # Ensure all registered players' inputs are reset
                 self.player_inputs[p_name_key] = None
            
            # Reset synchronization flags for the new attempt
            self.timeout_has_fired_for_current_attempt = False
            self.submissions_processed_for_current_attempt = False

            seq_str = "".join(self.current_stratagem['sequence_keys'])
            msg_to_broadcast = f"STRATAGEM_INFO {self.current_stratagem['name']}|{self.current_stratagem['display']}|{seq_str}|{self.current_time_limit}"
            
            log_action_prefix = "First" if initial_call else ("Next (after SUCCESS)" if outcome_previous_round == "SUCCESS" else "New (after FAIL)")
            # CRITICAL LOG: Confirming new stratagem selection and broadcast attempt
            print(f"[SERVER LOG] {log_action_prefix} Stratagem: {self.current_stratagem['name']} ({seq_str}). Time: {self.current_time_limit}s. Broadcasting to clients.")
            self._broadcast_nolock(msg_to_broadcast) # CRITICAL BROADCAST

            # Cancel previous timer if exists and start new one
            if self.round_timer: self.round_timer.cancel()
            self.round_timer = threading.Timer(self.current_time_limit, self.handle_timeout)
            self.round_timer.daemon = True # Ensure timer doesn't block program exit
            self.round_timer.start()
            print(f"[SERVER DEBUG] New round timer started for {self.current_time_limit}s for {self.current_stratagem['name']}.")
        print(f"[SERVER DEBUG] pick_new_random_stratagem END.")


    def process_player_input(self, player_name, sequence):
        with self.lock:
            current_strat_name_for_log = self.current_stratagem['name'] if self.current_stratagem else "N/A"
            print(f"[SERVER DETAIL LOG] process_player_input: {player_name} for {current_strat_name_for_log}. Seq: {sequence}. Current server inputs snapshot: {self.player_inputs}")
            
            if not self.game_active or not self.current_stratagem or self.player_inputs.get(player_name) is not None: # Already submitted this attempt
                return

            self.player_inputs[player_name] = sequence # Store the input
            
            all_players_submitted = True
            # Get currently connected player names for checking submission status
            active_player_names_list = [p_info['name'] for p_info in self.clients.values()]
            if not active_player_names_list: 
                print("[SERVER WARNING] No active players found during process_player_input check."); return

            for p_name_check in active_player_names_list:
                if self.player_inputs.get(p_name_check) is None: # Check if this player has submitted
                    all_players_submitted = False; break
            
            if all_players_submitted:
                print(f"[SERVER LOG] All players ({active_player_names_list}) submitted for {current_strat_name_for_log}.")
                if self.timeout_has_fired_for_current_attempt: 
                    print(f"[SERVER LOG] Submissions for {current_strat_name_for_log} were completed, but timeout had already processed this attempt. No action from submission path.")
                else:
                    # Submissions beat the timeout's action
                    if self.round_timer: self.round_timer.cancel() 
                    self.submissions_processed_for_current_attempt = True # Mark that submissions will handle outcome
                    print(f"[SERVER LOG] Evaluating inputs for {current_strat_name_for_log} (submissions complete).")
                    self.evaluate_inputs() # Proceed to evaluate

    def handle_timeout(self):
        with self.lock: 
            if not self.game_active or not self.current_stratagem: return

            current_strat_name_for_log = self.current_stratagem['name']
            print(f"[SERVER DEBUG] handle_timeout triggered for {current_strat_name_for_log}. Submissions processed flag: {self.submissions_processed_for_current_attempt}")

            if self.submissions_processed_for_current_attempt: # If submissions path already handled this round
                print(f"[SERVER LOG] Timeout for {current_strat_name_for_log}, but submissions were already processed and evaluated. Timeout action ignored.")
                return 

            self.timeout_has_fired_for_current_attempt = True # Mark that timeout is handling this attempt
            print(f"[SERVER LOG] Timeout for Stratagem: {current_strat_name_for_log}. Player inputs at timeout: {self.player_inputs}")
            
            all_inputs_actually_present_at_timeout = True
            active_player_names_list_timeout = [p_info['name'] for p_info in self.clients.values()]
            if not active_player_names_list_timeout and self.game_active: # No players left
                 print("[SERVER LOG] handle_timeout: No active players during timeout check, ending game."); self.game_active = False; self.game_over_flag = True; return

            for p_name_val_timeout in active_player_names_list_timeout:
                if self.player_inputs.get(p_name_val_timeout) is None: 
                    all_inputs_actually_present_at_timeout = False; break
            
            if all_inputs_actually_present_at_timeout and active_player_names_list_timeout:
                # Rare case: all inputs arrived just as timeout hits, but submission path didn't set its flag yet
                print(f"[SERVER LOG] handle_timeout: All inputs for {current_strat_name_for_log} found present during timeout check. Evaluating them.")
                self.evaluate_inputs() # Let evaluate_inputs decide based on present data
            else:

                print(f"[SERVER LOG] Timeout for {current_strat_name_for_log} is valid (some inputs missing). Assigning new random stratagem.")
                self._broadcast_nolock(f"ROUND_FAIL Timeout! Stratagem {current_strat_name_for_log} failed. A new Stratagem will be assigned.")
                
                # Critical logging for the call to pick new stratagem
                print(f"[SERVER CRITICAL DEBUG] BEFORE calling pick_new_random_stratagem from handle_timeout for {current_strat_name_for_log}")
                self.pick_new_random_stratagem(outcome_previous_round="FAIL")
                print(f"[SERVER CRITICAL DEBUG] AFTER calling pick_new_random_stratagem from handle_timeout for {current_strat_name_for_log}")

    def evaluate_inputs(self): 
        # THIS FUNCTION'S LOGS ARE CRITICAL TO SEE IN YOUR NEXT SERVER OUTPUT
        with self.lock:
            if not self.game_active or not self.current_stratagem:
                print("[SERVER LOG] evaluate_inputs: Called when not active or no current stratagem. Returning."); return
            
            current_strat_name_for_log = self.current_stratagem['name']
            expected_sequence = "".join(self.current_stratagem['sequence_keys'])
            # CRITICAL LOG: Show what inputs are being evaluated
            print(f"[SERVER EVAL LOG] Evaluating inputs for {current_strat_name_for_log}. Expected: '{expected_sequence}'. Actual Player Inputs Snapshot: {dict(self.player_inputs)}")
            
            all_players_correct = True
            active_player_names_list_eval = [p_info['name'] for p_info in self.clients.values()]
            
            if not active_player_names_list_eval and self.game_active: # No players left mid-evaluation
                print("[SERVER EVAL LOG] No active players found during evaluation, ending game."); self.game_active=False; self.game_over_flag=True; return

            if not active_player_names_list_eval: # If list is empty (e.g. all disconnected)
                print("[SERVER EVAL LOG] No active players to evaluate inputs for."); all_players_correct = False # Treat as incorrect if no one to check

            # Check each active player's input
            for player_name_to_check in active_player_names_list_eval:
                player_actual_input_sequence = self.player_inputs.get(player_name_to_check)
                print(f"[SERVER EVAL DETAIL] Checking Player {player_name_to_check}: Input '{player_actual_input_sequence}', Expected '{expected_sequence}'")
                if player_actual_input_sequence is None: 
                    print(f"[SERVER EVAL LOG] Input for {player_name_to_check} is None during evaluation of {current_strat_name_for_log}. Marking as overall incorrect.")
                    all_players_correct = False; break 
                if player_actual_input_sequence != expected_sequence:
                    print(f"[SERVER EVAL LOG] Incorrect input detected for player {player_name_to_check} during evaluation of {current_strat_name_for_log}. Got: '{player_actual_input_sequence}'")
                    all_players_correct = False; break
            
            # Decision point based on evaluation
            if all_players_correct and active_player_names_list_eval: # Ensure there were players and all were correct
                print(f"[SERVER EVAL LOG] RESULT: All players correct for {current_strat_name_for_log}.")
                self._broadcast_nolock(f"ROUND_SUCCESS Stratagem {current_strat_name_for_log} successful! Preparing next assignment...")
                print(f"[SERVER DEBUG] evaluate_inputs calling pick_new_random_stratagem (outcome: SUCCESS) for {current_strat_name_for_log}")
                self.pick_new_random_stratagem(outcome_previous_round="SUCCESS")
                print(f"[SERVER DEBUG] evaluate_inputs returned from pick_new_random_stratagem (SUCCESS path) for {current_strat_name_for_log}")
            else:
                # This path if not all correct OR if active_player_names_list_eval was empty initially
                print(f"[SERVER EVAL LOG] RESULT: Input evaluation failed for {current_strat_name_for_log} (all_correct flag: {all_players_correct}, number of active_players: {len(active_player_names_list_eval)}).")
                self._broadcast_nolock(f"ROUND_FAIL Input was incorrect or incomplete for {current_strat_name_for_log}! A new Stratagem will be assigned.")
                print(f"[SERVER DEBUG] evaluate_inputs calling pick_new_random_stratagem (outcome: FAIL) for {current_strat_name_for_log}")
                self.pick_new_random_stratagem(outcome_previous_round="FAIL")
                print(f"[SERVER DEBUG] evaluate_inputs returned from pick_new_random_stratagem (FAIL path) for {current_strat_name_for_log}")

    def run(self):
        self.server_socket.listen(MIN_PLAYERS + 3) 
        print(f"Server listening on {HOST}:{PORT}")
        print(f"Waiting for at least {MIN_PLAYERS} players to join.")
        print(f"Game will be won after {self.target_deployments_to_win} successful Stratagem deployments.")
        try:
            while not self.game_over_flag :
                with self.lock: can_accept_new_conn = len(self.clients) < (MIN_PLAYERS + 3) # Allow some buffer
                
                if can_accept_new_conn : 
                    try:
                        self.server_socket.settimeout(1.0) # Timeout to allow checking game_over_flag
                        new_client_socket, new_client_address = self.server_socket.accept()
                        new_client_socket.settimeout(None) # Remove timeout for client specific socket

                        client_thread = threading.Thread(target=self.handle_client, args=(new_client_socket, new_client_address), daemon=True)
                        client_thread.start()
                    except socket.timeout: 
                        continue # Normal timeout, check game_over_flag and loop
                    except OSError as e: # More general socket error
                        if self.game_over_flag: # If server is shutting down, this can happen
                            print("[SERVER INFO] Server socket closed during shutdown accept.")
                            break
                        else: 
                            print(f"[SERVER ERROR] Server socket accept/setup error: {e}"); raise e # Re-raise if unexpected
                else: 
                    # Max clients or not accepting new ones, just sleep a bit
                    time.sleep(0.1) 
        except KeyboardInterrupt: 
            print("\n[SERVER INFO] Shutdown initiated by user (Ctrl+C)...")
        finally:
            print("[SERVER INFO] Initiating server shutdown sequence...")
            self.game_over_flag = True # Signal all threads to stop
            if self.round_timer: self.round_timer.cancel() # Stop any active round timer
            
            with self.lock: # Gracefully close client connections
                connections_to_close = list(self.clients.keys())
                for conn_socket_to_close in connections_to_close:
                    try:
                        conn_socket_to_close.sendall("GAME_END Server is shutting down now.".encode('utf-8'))
                        conn_socket_to_close.close()
                    except Exception as e_conn_close:
                        print(f"[SERVER ERROR] Error closing a client connection during shutdown: {e_conn_close}")
                self.clients.clear() # Clear the client list
            
            if self.server_socket: 
                self.server_socket.close() # Close the main server socket
            print("[SERVER INFO] Server shutdown complete.")

if __name__ == "__main__":
    if not STRATAGEM_LIST: 
        print("[SERVER FATAL ERROR] Stratagem list is empty. Please check stratagems.py.")
    else: 
        server = StratagemServer()
        server.run()