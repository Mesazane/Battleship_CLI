import os
import socket
import re
from protocol import pack_message, unpack_message, ProtocolError

HOST = os.getenv('GAME_HOST', '127.0.0.1')
PORT = int(os.getenv('GAME_PORT', '12345'))
GRID = 8


def input_coords(prompt):
    """Accept input in 'A,1' or '1,A' format for an 8x8 grid."""
    while True:
        line = input(prompt).strip()
        parts = [p.strip() for p in re.split(r'[ ,;]+', line)]
        if len(parts) != 2:
            print("Format 'A,1' or '1,A'.")
            continue
        rstr, cstr = parts
        if rstr.isalpha():
            r = ord(rstr.upper()) - 65
        else:
            try:
                r = int(rstr) - 1
            except ValueError:
                print("Row A-H or 1-8.")
                continue
        try:
            c = int(cstr) - 1
        except ValueError:
            print("Kolom 1-8.")
            continue
        if 0 <= r < GRID and 0 <= c < GRID:
            return r, c
        print("Coordinates are outside the range of A1-H8.")


def main():
    """Run the client: join, place ships, then play turn-based Battleship."""
    name = input("Enter your name: ").strip()
    ships = []
    print("Place 3 ships:")
    while len(ships) < 3:
        r, c = input_coords(f"Ship {len(ships)+1}: ")
        if (r, c) in ships:
            print("Unable to place ship, There's another ship already located in that location.")
            continue
        ships.append((r, c))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
        except Exception as e:
            print(f"Connection error: {e}")
            return
        try:
            s.sendall(pack_message('JOIN', name))
            # WAIT for PLACE prompt
            msg, info = unpack_message(s)
            if msg != 'PLACE':
                print(f"Unexpected server message: {msg} {info}")
                return
            # send placement
            placements = ';'.join(f"{r},{c}" for r, c in ships)
            s.sendall(pack_message('PLACED', placements))

            # WAIT or READY
            msg, info = unpack_message(s)
            if msg == 'WAIT':
                print(info)
                msg, info = unpack_message(s)
            if msg != 'READY':
                print(f"Unexpected server message: {msg} {info}")
                return
            print(f"Game start! Opponent: {info}")

            # Game loop
            while True:
                msg, data = unpack_message(s)
                if msg == 'YOUR_TURN':
                    r, c = input_coords("Your move: ")
                    s.sendall(pack_message('FIRE', f"{r},{c}"))
                elif msg == 'HIT':
                    r, c = map(int, data.split(','))
                    print(f"Hit at {chr(r+65)}{c+1}!")
                elif msg == 'MISS':
                    r, c = map(int, data.split(','))
                    print(f"Miss at {chr(r+65)}{c+1}.")
                elif msg == 'INCOMING_HIT':
                    r, c = map(int, data.split(','))
                    print(f"Opponent hit at {chr(r+65)}{c+1}!")
                elif msg == 'INCOMING_MISS':
                    r, c = map(int, data.split(','))
                    print(f"Opponent miss at {chr(r+65)}{c+1}.")
                elif msg == 'END':
                    print(data)
                    break
                elif msg == 'ERROR':
                    print(f"Server error: {data}")
                    break
                else:
                    print(f"Unknown message: {msg} {data}")
        except ProtocolError as e:
            print(f"Protocol error: {e}")
        except ConnectionError:
            print("Connection lost.")
        except Exception as e:
            print(f"Unexpected client error: {e}")

if __name__ == '__main__':
    main()