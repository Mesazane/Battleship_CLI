import socket
import struct
from protocol import pack_message, unpack_message, ProtocolError

def send_email(winner_name):
    import os
    import smtplib
    from email.message import EmailMessage

    EMAIL = os.getenv('BS_EMAIL')
    PASS = os.getenv('BS_EMAIL_PASS')
    TO = os.getenv('BS_NOTIFY_TO')

    msg = EmailMessage()
    msg.set_content(f"Player {winner_name} has won the Battleship game!")
    msg['Subject'] = "🏴‍☠️ Battleship Victory 🏴‍☠️"
    msg['From'] = EMAIL
    msg['To'] = TO

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL, PASS)
        smtp.send_message(msg)


def print_board(board):
    size = len(board)
    header = '  ' + ' '.join(str(i) for i in range(size))
    print(header)
    for idx,row in enumerate(board):
        print(f"{idx} " + ' '.join('X' if cell else '~' for cell in row))


def main():
    host = input("Server IP [default 127.0.0.1]: ").strip() or '127.0.0.1'
    port = 9999
    name = input("Your name: ").strip()
    sock = socket.socket()
    sock.connect((host, port))
    sock.sendall(name.encode())

    # initialize boards
    own_hits = [[False]*5 for _ in range(5)]
    opp_hits = [[False]*5 for _ in range(5)]

    print("Waiting for another player to join...")

    while True:
        hdr = sock.recv(8)
        if not hdr:
            break
        try:
            msg_type, data = unpack_message(hdr + sock.recv(struct.unpack('!4sI', hdr)[1]))
        except ProtocolError as e:
            print("Protocol error:", e)
            break

        if msg_type == 'YOUR_TURN':
            print("\nYour Board Hits:")
            print_board(own_hits)
            print("Opponent Board Hits:")
            print_board(opp_hits)
            # input attack
            coords = input("Enter attack coord (row,col): ")
            sock.sendall(pack_message('ATTACK', coords))

        elif msg_type == 'RESULT':
            res, r, c = data.split(',')
            r, c = int(r), int(c)
            own_hits[r][c] = (res == 'HIT')
            print(f"You {'hit' if res=='HIT' else 'missed'} at {r},{c}")

        elif msg_type == 'OPPONENT_MOVE':
            res, r, c = data.split(',')
            r, c = int(r), int(c)
            opp_hits[r][c] = (res == 'HIT')
            print(f"Opponent {'hit' if res=='HIT' else 'missed'} your ship at {r},{c}")

        elif msg_type == 'GAME_OVER':
            winner = data
            print(f"\nGame Over! Winner: {winner}")
            if winner == name:
                send_email(name)
            break

        else:
            continue

    sock.close()

if __name__ == '__main__':
    main()