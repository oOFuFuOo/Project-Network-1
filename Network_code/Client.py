import socket
import sys
import threading

ROWS = 6
COLS = 7

STATUS_PHRASES = {
    "100": "WELCOME",
    "101": "WAITING_FOR_OPPONENT",
    "200": "GAME_START",
    "202": "YOUR_TURN",
    "204": "OPPONENT_TURN",
    "205": "STATE",
    "210": "MOVE_OK",
    "220": "WIN",
    "221": "DRAW",
    "400": "INVALID_COLUMN",
    "401": "COLUMN_FULL",
    "402": "INVALID_COMMAND",
    "403": "NOT_YOUR_TURN",
    "404": "GAME_NOT_STARTED",
    "599": "OPPONENT_DISCONNECTED",
}


def print_board(board_str):
    print()
    for r in range(ROWS):
        row_cells = board_str[r * COLS:(r + 1) * COLS]
        print(" | ".join(row_cells))
    print("  " + "   ".join(str(c) for c in range(1, COLS + 1)))
    print()


class ConnectFourClient:
    def __init__(self, host, port, name):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.rfile = self.sock.makefile("r", encoding="utf-8")
        self.is_my_turn = False
        self.game_over = False
        self.symbol = None
        self.board = [["." for _ in range(COLS)] for _ in range(ROWS)]

    def send(self, line):
        print(f"[SENT] {line}")
        self.sock.sendall((line + "\n").encode("utf-8"))

    def recv_loop(self):
        while True:
            line = self.rfile.readline()
            if not line:
                print("[INFO] Connection closed by server.")
                self.game_over = True
                break
            line = line.strip()
            code = line.split(" ", 1)[0]
            phrase = STATUS_PHRASES.get(code, "UNKNOWN")
            print(f"[RECV] {code} {phrase} | {line}")
            self.handle_message(code, line)

    def handle_message(self, code, line):
        if code == "100":
            _, _, player_no, symbol = line.split(" ")
            self.symbol = symbol
            print(f"[INFO] You are Player {player_no}, symbol '{symbol}'")
        elif code == "205":
            _, _, board_str, turn_symbol, state = line.split(" ")
            for r in range(ROWS):
                for c in range(COLS):
                    self.board[r][c] = board_str[r * COLS + c]
            print_board(board_str)
            print(f"[INFO] state={state} turn={turn_symbol}")
        elif code == "210":
            _, _, col_ext, row, symbol = line.split(" ")
            row = int(row)
            col0 = int(col_ext) - 1
            self.board[row][col0] = symbol
            print_board("".join("".join(r) for r in self.board))
        elif code == "202":
            self.is_my_turn = True
        elif code == "204":
            self.is_my_turn = False
        elif code in ("220", "221", "599"):
            self.game_over = True
            if code == "220":
                _, _, symbol, name = line.split(" ", 3)
                print(f"[RESULT] {name} ({symbol}) WINS!")
            elif code == "221":
                print("[RESULT] Game ended in a DRAW.")
            else:
                print("[RESULT] Opponent disconnected. Game over.")
        elif code in ("400", "401", "402", "403", "404"):
            print(f"[WARN] Request rejected: {STATUS_PHRASES.get(code, 'UNKNOWN')}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <server_ip> <port> [name]")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else input("Enter your name: ")

    client = ConnectFourClient(host, port, name)
    threading.Thread(target=client.recv_loop, daemon=True).start()

    client.send(f"HELLO {name}")

    try:
        while not client.game_over:
            turn_label = "your turn" if client.is_my_turn else "opponent's turn"
            try:
                choice = input(
                    f"[{name}] ({turn_label}) column (1-{COLS}), 's' for STATE, 'q' to quit: "
                ).strip()
            except EOFError:
                break
            if client.game_over:
                break
            if choice.lower() == "q":
                client.send("QUIT")
                break
            if choice.lower() == "s":
                client.send("STATE")
                continue
            if not choice.isdigit() or not (1 <= int(choice) <= COLS):
                print(f"[WARN] Please enter a number between 1 and {COLS}.")
                continue
            client.send(f"MOVE {choice}")
    except KeyboardInterrupt:
        client.send("QUIT")
    finally:
        client.sock.close()
        print("[INFO] Disconnected. Goodbye!")


if __name__ == "__main__":
    main()