import socket
import threading
import struct
from protocol import pack_message, unpack_message, ProtocolError

HOST = '0.0.0.0'
PORT = 9999
GRID_SIZE = 5
SHIP_SIZES = [3, 2]  # two ships: length 3 and 2

class Game:
    def __init__(self, players):
        self.players = players  # list of (conn, name)
        self.boards = {name: [[False]*GRID_SIZE for _ in range(GRID_SIZE)]
                       for _, name in players}
        self.hits = {name: [[False]*GRID_SIZE for _ in range(GRID_SIZE)]
                     for _, name in players}
        self.turn = 0  # index in players
        self.place_all_ships()

    def place_all_ships(self):
        # For simplicity: server randomly places ships for each player
        import random
        for conn, name in self.players:
            coords = []
            for size in SHIP_SIZES:
                placed = False
                while not placed:
                    orientation = random.choice(['H','V'])
                    if orientation=='H':
                        row = random.randrange(GRID_SIZE)
                        col = random.randrange(GRID_SIZE-size+1)
                        ship_coords = [(row, col+i) for i in range(size)]
                    else:
                        row = random.randrange(GRID_SIZE-size+1)
                        col = random.randrange(GRID_SIZE)
                        ship_coords = [(row+i, col) for i in range(size)]
                    # check overlap
                    if all(not self.boards[name][r][c] for r,c in ship_coords):
                        for r,c in ship_coords:
                            self.boards[name][r][c] = True
                        placed = True

    def broadcast(self, msg_type, data):
        for conn, _ in self.players:
            conn.sendall(pack_message(msg_type, data))

    def other(self, idx):
        return (idx + 1) % len(self.players)

    def all_sunk(self, name):
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if self.boards[name][r][c] and not self.hits[name][r][c]:
                    return False
        return True

    def handle(self):
        while True:
            conn, name = self.players[self.turn]
            try:
                # ask for attack
                conn.sendall(pack_message('YOUR_TURN', ''))
                # receive attack
                hdr = conn.recv(8)
                if not hdr:
                    break
                _, length = struct.unpack('!4sI', hdr)
                body = conn.recv(length)
                msg_type, data = unpack_message(hdr+body)
                if msg_type != 'ATTACK':
                    continue
                row, col = map(int, data.split(','))
                opp_idx = self.other(self.turn)
                _, opp_name = self.players[opp_idx]
                hit = self.boards[opp_name][row][col]
                self.hits[opp_name][row][col] = True
                result = 'HIT' if hit else 'MISS'
                # notify both
                conn.sendall(pack_message('RESULT', f"{result},{row},{col}"))
                oconn, _ = self.players[opp_idx]
                oconn.sendall(pack_message('OPPONENT_MOVE', f"{result},{row},{col}"))
                # check win
                if self.all_sunk(opp_name):
                    self.broadcast('GAME_OVER', name)
                    break
                # next turn
                self.turn = opp_idx
            except Exception as e:
                print(f"[!] Error in game: {e}")
                break
        # close connections
        for conn,_ in self.players:
            conn.close()


def handle_client(conn, addr, waiting):
    try:
        # get player name
        name = conn.recv(1024).decode().strip()
        print(f"Connected: {name} @ {addr}")
        waiting.append((conn, name))
        if len(waiting) == 2:
            game = Game(waiting.copy())
            threading.Thread(target=game.handle, daemon=True).start()
            waiting.clear()
    except Exception as e:
        print(f"[!] Client error: {e}")
        conn.close()


def main():
    waiting = []
    sock = socket.socket()
    sock.bind((HOST, PORT))
    sock.listen()
    print(f"Server listening on {HOST}:{PORT}")
    try:
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=handle_client, args=(conn, addr, waiting), daemon=True).start()
    except KeyboardInterrupt:
        print("Shutting down server.")
    finally:
        sock.close()

if __name__ == '__main__':
    main()