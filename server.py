import os
import socket
import threading
import smtplib
import ssl
import getpass
from email.message import EmailMessage
from protocol import recv_all, pack_message, unpack_message, ProtocolError

HOST = '0.0.0.0'
PORT = 12345
lobby = []
lobby_lock = threading.Lock()


EMAIL_HOST = os.getenv('EMAIL_HOST') or input("SMTP server (e.g. smtp.gmail.com): ")
EMAIL_PORT = int(os.getenv('EMAIL_PORT') or input("SMTP port (e.g. 465): "))
EMAIL_USER = os.getenv('EMAIL_USER') or input("Sender email: ")
EMAIL_PASS = os.getenv('EMAIL_PASS') or getpass.getpass(f"Password for {EMAIL_USER}: ")
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER') or input("Receiver email: ")


def send_email(subject: str, body: str):
    if not all([EMAIL_HOST, EMAIL_USER, EMAIL_PASS, EMAIL_RECEIVER]):
        print("Email config incomplete, skipping email.")
        return
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_RECEIVER
        msg.set_content(body)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=ctx) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def handle_client(conn: socket.socket, addr):
    try:
        # 1) JOIN
        msg, name = unpack_message(conn)
        if msg != 'JOIN':
            conn.sendall(pack_message('ERROR', 'Expected JOIN'))
            return
        # 2) PLACE
        conn.sendall(pack_message('PLACE', 'Place your 3 ships (A-H,1-8)'))
        msg, data = unpack_message(conn)
        if msg != 'PLACED':
            conn.sendall(pack_message('ERROR', 'Expected PLACED'))
            return
        ships = [tuple(map(int, p.split(','))) for p in data.split(';')]

        # 3) Entering lobby
        with lobby_lock:
            lobby.append({'conn': conn, 'name': name, 'ships': ships})
            if len(lobby) < 2:
                conn.sendall(pack_message('WAIT', 'Waiting for opponent…'))

        # 4) Pairing
        while True:
            with lobby_lock:
                if len(lobby) >= 2:
                    p1 = lobby.pop(0)
                    p2 = lobby.pop(0)
                    break
        threading.Thread(target=game_thread, args=(p1, p2), daemon=True).start()

    except ProtocolError as e:
        conn.sendall(pack_message('ERROR', str(e)))
    except ConnectionError:
        print(f"[{addr}] Connection closed unexpectedly.")
    finally:
        pass

def game_thread(p1, p2):
    players = [p1, p2]
    # Send READY signal to both players
    for p in players:
        opp = p2 if p is p1 else p1
        p['conn'].sendall(pack_message('READY', opp['name']))

    turn = 0
    try:
        while True:
            atk = players[turn]
            defn = players[1 - turn]

            # Trun to Attack
            atk['conn'].sendall(pack_message('YOUR_TURN', 'Your move'))
            msg, coord = unpack_message(atk['conn'])
            if msg != 'FIRE':
                raise ProtocolError('Expected FIRE')
            r, c = map(int, coord.split(','))
            hit = (r, c) in defn['ships']

            if hit:
                defn['ships'].remove((r, c))
                atk['conn'].sendall(pack_message('HIT', coord))
                defn['conn'].sendall(pack_message('INCOMING_HIT', coord))

                # Win check
                if not defn['ships']:
                    winner = atk; loser = defn
                    # Subject + body
                    subject = f"🎉 Congrats! You've won a game of Battleship!"
                    body = (
                        f"Selamat {winner['name']}! You've won a game of Battleship!\n"
                        f"Winner: {winner['name']}\n"
                        f"Loser: {loser['name']}\n"
                    )
                    threading.Thread(
                        target=send_email,
                        args=(subject, body),
                        daemon=True
                    ).start()

                    # Send END message
                    winner['conn'].sendall(pack_message('END', 'You win!'))
                    loser['conn'].sendall(pack_message('END', 'You lose.'))
                    break
            else:
                atk['conn'].sendall(pack_message('MISS', coord))
                defn['conn'].sendall(pack_message('INCOMING_MISS', coord))

            turn = 1 - turn

    except ProtocolError as e:
        for p in players:
            p['conn'].sendall(pack_message('ERROR', str(e)))
    except ConnectionError:
        print("Game connection lost unexpectedly.")
    finally:
        for p in players:
            p['conn'].close()

def main():
    print(f"Server listening on {HOST}:{PORT}")
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            print(f"Connection from {addr}")
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    main()
