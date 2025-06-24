import os
import socket
import threading
import smtplib
import ssl
from email.message import EmailMessage
from protocol import recv_all, pack_message, unpack_message, ProtocolError

HOST = '0.0.0.0'
PORT = 12345
lobby = []  # list of dicts: {'conn', 'name', 'ships'}
lobby_lock = threading.Lock()

# Email configuration from environment variables
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '465'))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER')

def send_email(subject: str, body: str):
    """Send an email notification using SMTP SSL."""
    if not all([EMAIL_HOST, EMAIL_USER, EMAIL_PASS, EMAIL_RECEIVER]):
        print("Email config incomplete, skipping email.")
        return
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_RECEIVER
        msg.set_content(body)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def handle_client(conn: socket.socket, addr):
    """Handle a new client connection: join, place ships, then wait for game pairing."""
    try:
        msg, name = unpack_message(conn)
        if msg != 'JOIN':
            conn.sendall(pack_message('ERROR', 'Expected JOIN'))
            conn.close()
            return
        # Ask for ship placement
        conn.sendall(pack_message('PLACE', 'Place your 3 ships (A-H,1-8)'))
        msg, data = unpack_message(conn)
        if msg != 'PLACED':
            conn.sendall(pack_message('ERROR', 'Expected PLACED'))
            conn.close()
            return
        ships = [tuple(map(int, p.split(','))) for p in data.split(';')]
        with lobby_lock:
            lobby.append({'conn': conn, 'name': name, 'ships': ships})
            if len(lobby) < 2:
                conn.sendall(pack_message('WAIT', 'Waiting for opponent...'))
        # Wait until two players ready
        while True:
            with lobby_lock:
                if len(lobby) >= 2:
                    p1 = lobby.pop(0)
                    p2 = lobby.pop(0)
                    break
        threading.Thread(target=game_thread, args=(p1, p2), daemon=True).start()
    except ProtocolError as e:
        print(f"[{addr}] Protocol error: {e}")
        try:
            conn.sendall(pack_message('ERROR', str(e)))
        except:
            pass
        conn.close()
    except ConnectionError:
        print(f"[{addr}] Connection closed unexpectedly.")
        conn.close()
    except Exception as e:
        print(f"[{addr}] Unexpected error: {e}")
        conn.close()


def game_thread(p1: dict, p2: dict):
    """Run the main game loop for two players."""
    players = [p1, p2]
    # Notify both that game is ready
    for p in players:
        opp = p2 if p is p1 else p1
        try:
            p['conn'].sendall(pack_message('READY', opp['name']))
        except Exception as e:
            print(f"Error sending READY to {p['name']}: {e}")
            return
    turn = 0
    try:
        while True:
            attacker = players[turn]
            defender = players[1 - turn]
            # Prompt attacker for move
            attacker['conn'].sendall(pack_message('YOUR_TURN', 'Your move'))
            msg, coord = unpack_message(attacker['conn'])
            if msg != 'FIRE':
                raise ProtocolError('Expected FIRE')
            r, c = map(int, coord.split(','))
            hit = (r, c) in defender['ships']
            if hit:
                defender['ships'].remove((r, c))
                attacker['conn'].sendall(pack_message('HIT', coord))
                defender['conn'].sendall(pack_message('INCOMING_HIT', coord))
                if not defender['ships']:
                    attacker['conn'].sendall(pack_message('END', 'You win!'))
                    defender['conn'].sendall(pack_message('END', 'You lose.'))
                    threading.Thread(
                        target=send_email,
                        args=(f"{attacker['name']} won Battleship!",
                              f"Player {attacker['name']} has won the game against {defender['name']}."),
                        daemon=True
                    ).start()
                    break
            else:
                attacker['conn'].sendall(pack_message('MISS', coord))
                defender['conn'].sendall(pack_message('INCOMING_MISS', coord))
            turn = 1 - turn
    except ProtocolError as e:
        print(f"Game protocol error: {e}")
        for p in players:
            try:
                p['conn'].sendall(pack_message('ERROR', str(e)))
            except:
                pass
    except ConnectionError:
        print("Game connection lost unexpectedly.")
    except Exception as e:
        print(f"Unexpected game error: {e}")
    finally:
        for p in players:
            try:
                p['conn'].close()
            except:
                pass


def main():
    """Start the server and listen for client connections."""
    print(f"Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        while True:
            try:
                conn, addr = s.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except KeyboardInterrupt:
                print("Server shutting down.")
                break
            except Exception as e:
                print(f"Accept error: {e}")

if __name__ == '__main__':
    main()