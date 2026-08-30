import socket
import threading

HOST = "0.0.0.0"
PORT = 5555
ROWS = 6
COLS = 7


def log(msg):
    print(f"[SERVER] {msg}")


class ConnectFourGame:
    def __init__(self):
        self.board = [["." for _ in range(COLS)] for _ in range(ROWS)]
        self.turn = 0
        self.players = []
        self.lock = threading.Lock()
        self.state = "WAITING"
        self.ready_event = threading.Event()

    def board_string(self):
        return "".join("".join(row) for row in self.board)

    def drop_piece(self, col0, symbol):
        for row in range(ROWS - 1, -1, -1):
            if self.board[row][col0] == ".":
                self.board[row][col0] = symbol
                return row
        return None

    def check_win(self, row, col0, symbol):
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in directions:
            count = 1
            for sign in (1, -1):
                r, c = row + dr * sign, col0 + dc * sign
                while 0 <= r < ROWS and 0 <= c < COLS and self.board[r][c] == symbol:
                    count += 1
                    r += dr * sign
                    c += dc * sign
            if count >= 4:
                return True
        return False

    def is_full(self):
        return all(self.board[0][c] != "." for c in range(COLS))


class PlayerHandler(threading.Thread):
    def __init__(self, conn, addr, player_no, symbol, game):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.player_no = player_no
        self.symbol = symbol
        self.game = game
        self.name = f"Player{player_no}"
        self.rfile = conn.makefile("r", encoding="utf-8")

    def send(self, line):
        log(f"-> {self.name}: {line}")
        try:
            self.conn.sendall((line + "\n").encode("utf-8"))
        except OSError:
            pass

    def recv_line(self):
        line = self.rfile.readline()
        if not line:
            return None
        return line.strip()

    def run(self):
        try:
            line = self.recv_line()
            if not line or not line.startswith("HELLO "):
                self.send("402 INVALID_COMMAND expected HELLO")
                self.conn.close()
                return
            self.name = line.split(" ", 1)[1].strip() or self.name
            log(f"<- {self.name}: {line}")
            self.send(f"100 WELCOME {self.player_no} {self.symbol}")

            if self.player_no == 0:
                self.send("101 WAITING_FOR_OPPONENT")

            self.game.ready_event.wait()

            if self.player_no == 0:
                with self.game.lock:
                    self.game.state = "PLAYING"
                first = self.game.players[self.game.turn]
                for p in self.game.players:
                    p.send(f"200 GAME_START {first.name}")
                self._notify_turn()

            while True:
                line = self.recv_line()
                if line is None:
                    self._handle_disconnect()
                    return
                log(f"<- {self.name}: {line}")

                if line == "QUIT":
                    self._handle_disconnect()
                    return
                elif line == "STATE":
                    self._handle_state()
                elif line.startswith("MOVE "):
                    self._handle_move(line)
                else:
                    self.send("402 INVALID_COMMAND unknown request")

        except (ConnectionResetError, BrokenPipeError):
            self._handle_disconnect()

    def _notify_turn(self):
        for i, p in enumerate(self.game.players):
            if i == self.game.turn:
                p.send("202 YOUR_TURN")
            else:
                p.send("204 OPPONENT_TURN")

    def _handle_state(self):
        with self.game.lock:
            turn_symbol = self.game.players[self.game.turn].symbol if self.game.players else "-"
            self.send(f"205 STATE {self.game.board_string()} {turn_symbol} {self.game.state}")

    def _handle_move(self, line):
        with self.game.lock:
            if self.game.state != "PLAYING":
                self.send("404 GAME_NOT_STARTED")
                return
            if self.game.players[self.game.turn] is not self:
                self.send("403 NOT_YOUR_TURN")
                return
            try:
                col_ext = int(line.split(" ", 1)[1].strip())
            except (IndexError, ValueError):
                self.send("400 INVALID_COLUMN")
                return

            col0 = col_ext - 1
            if col0 < 0 or col0 >= COLS:
                self.send("400 INVALID_COLUMN")
                return

            row = self.game.drop_piece(col0, self.symbol)
            if row is None:
                self.send("401 COLUMN_FULL")
                return

            for p in self.game.players:
                p.send(f"210 MOVE_OK {col_ext} {row} {self.symbol}")

            if self.game.check_win(row, col0, self.symbol):
                self.game.state = "OVER"
                for p in self.game.players:
                    p.send(f"220 WIN {self.symbol} {self.name}")
                return

            if self.game.is_full():
                self.game.state = "OVER"
                for p in self.game.players:
                    p.send("221 DRAW")
                return

            self.game.turn = (self.game.turn + 1) % 2
            self._notify_turn()

    def _handle_disconnect(self):
        log(f"{self.name} disconnected")
        with self.game.lock:
            if self.game.state != "OVER":
                self.game.state = "OVER"
                for p in self.game.players:
                    if p is not self:
                        p.send("599 OPPONENT_DISCONNECTED")
            if self in self.game.players:
                self.game.players.remove(self)
        try:
            self.conn.close()
        except OSError:
            pass


def main():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(2)
    log(f"C4P/1.0 Connect Four server listening on port {PORT}")

    while True:
        game = ConnectFourGame()
        symbols = ["X", "O"]
        log("Waiting for 2 players to start a new match...")
        for i in range(2):
            conn, addr = server_sock.accept()
            log(f"Player {i} connected from {addr}")
            handler = PlayerHandler(conn, addr, i, symbols[i], game)
            game.players.append(handler)
            handler.start()
        game.ready_event.set()


if __name__ == "__main__":
    main()