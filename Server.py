import tkinter as tk
from tkinter import scrolledtext, messagebox
import socket
import threading
import time

class ChatServer:
    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("Chat Server")
        master.grid_columnconfigure(index=list(range(2)), weight=1)
        master.grid_rowconfigure(index=list(range(4)), weight=1)

        self.server_socket = None
        self.is_listening = False
        self.clients = {}  # {client_socket: name}
        self.thread = None
        self.num_of_clients = 0
        self.game_started = False
        self.questions_list = []
        self.num_questions_to_ask = 0
        self.answers = {}
        self.expected_players = []
        self.answer_order = []
        self.waiting_for_answers = False
        self.scores = {}
        self.disconnected_names = []
        self.end_after_current_question = False
        self.create_widgets()

    def create_widgets(self):
        # Port frame
        port_frame = tk.Frame(self.master)
        port_frame.grid(row=0, column=0, pady=10, padx=10, sticky="EW")

        port_frame.grid_columnconfigure(0, weight=0, minsize=150)
        port_frame.grid_columnconfigure(1, weight=1)

        tk.Label(port_frame, text="Port:").grid(row=0, column=0, sticky="W")
        self.port_entry = tk.Entry(port_frame)
        self.port_entry.grid(row=0, column=1, sticky="W")

        # Message display
        self.listen_button = tk.Button(self.master, text="Listen", command=self.toggle_listening)
        self.listen_button.grid(row=0, column=1, pady=10, padx=10, sticky="EW")

        num_of_questions = tk.Frame(self.master)
        num_of_questions.grid(row=1, column=0, pady=10, padx=10, sticky="EW")

        num_of_questions.grid_columnconfigure(0, weight=0, minsize=150)
        num_of_questions.grid_columnconfigure(1, weight=1)

        tk.Label(num_of_questions, text="Number of Questions:").grid(row=0, column=0, sticky="W")
        self.num_questions_entry = tk.Entry(num_of_questions)
        self.num_questions_entry.grid(row=0, column=1, sticky="W")

        self.start_button = tk.Button(self.master, text="Start Game", command=self.toggle_game)
        self.start_button.grid(row=2, column=1, pady=10, padx=10, sticky="EW")

        file_frame = tk.Frame(self.master)
        file_frame.grid(row=2, column=0, pady=10, padx=10, sticky="EW")

        file_frame.grid_columnconfigure(0, weight=0, minsize=150)
        file_frame.grid_columnconfigure(1, weight=1)

        tk.Label(file_frame, text="Questions File:").grid(row=0, column=0, sticky="W")
        self.file_entry = tk.Entry(file_frame)
        self.file_entry.grid(row=0, column=1, sticky="EW")

        self.text_widget = tk.Text(self.master, state=tk.DISABLED)
        self.text_widget.grid(row=3, column=0, columnspan=2, pady=10, padx=10, sticky="NSEW")

    def toggle_listening(self):
        if self.is_listening:
            self.stop_listening()
        else:
            self.start_listening()

    def toggle_game(self):
        if self.game_started:
            self.stop_game()
        else:
            self.start_game()

    def start_game(self):
        # cannot start game if server is not listening
        if not self.is_listening:
            messagebox.showerror("Error", "Start listening first.")
            return

        # block starting again if game already started
        if self.game_started:
            messagebox.showerror("Error", "Game has already started.")
            return

        # at least 2 clients before starting
        if self.num_of_clients < 2:
            messagebox.showerror("Error", "There needs to be at least 2 players to be able to start the game.")
            return

        # read the questions file name from gui
        filename = self.get_filename()
        if filename is None:
            return

        # load and parse questions from the file
        questions = self.get_questions(filename)
        if questions is None or len(questions) == 0:
            messagebox.showerror("Error", "Could not load questions from the file.")
            return

        # read how many questions to ask from gui
        num_str = self.num_questions_entry.get().strip()
        if not num_str:
            messagebox.showerror("Error", "Please enter number of questions.")
            return

        # validate the number of questions input
        try:
            num_to_ask = int(num_str)
        except ValueError:
            messagebox.showerror("Error", "Number of questions must be an integer.")
            return

        # do not allow zero or negative question count
        if num_to_ask <= 0:
            messagebox.showerror("Error", "Number of questions must be positive.")
            return

        # save questions and question count
        self.questions_list = questions
        self.num_questions_to_ask = num_to_ask

        # reset answer tracking for a new game
        self.answers = {}
        self.expected_players = []
        self.answer_order = []
        self.waiting_for_answers = False
        self.end_after_current_question = False

        # reset scoreboard for a new game
        self.scores = {}
        for name in self.clients.values():
            self.scores[name] = 0

        # no new clients after game starts
        self.game_started = True
        self.start_button.config(text="Stop Game")

        # show start message on server and send to clients
        msg = f"--- Game started with {self.num_of_clients} players---"
        self.add_message_to_text(msg)
        self.broadcast(msg)

        # send initial scoreboard to everyone
        scoreboard_msg = self.build_scoreboard_message()
        self.add_message_to_text(scoreboard_msg.strip())
        self.broadcast(scoreboard_msg)

        # run the question loop in a separate thread
        question_thread = threading.Thread(target=self.give_questions, daemon=True)
        question_thread.start()

    def stop_game(self):
        # stop game and disconnect clients but keep server listening
        if self.game_started:
            self.game_started = False
            self.waiting_for_answers = False
            self.start_button.config(text="Start Game")

            msg = "--- Game stopped by server ---"
            self.add_message_to_text(msg)
            self.broadcast(msg)
            self.disconnect_all_clients_server_end()

    def build_scoreboard_message(self):
        # build a scoreboard message that clients can display
        msg = "SCOREBOARD\n"
        for name in sorted(self.scores.keys()):
            msg += name + ": " + str(self.scores[name]) + "\n"
        return msg

    def final_ranked_scoreboard(self):
        # sort scores in descending order for final ranking output
        items = list(self.scores.items())

        i = 0
        while i < len(items):
            j = i + 1
            while j < len(items):
                if items[j][1] > items[i][1]:
                    temp = items[i]
                    items[i] = items[j]
                    items[j] = temp
                j += 1
            i += 1

        # assign ranks and skip ranks after ties
        msg = "FINAL SCOREBOARD\n"

        rank = 1
        i = 0
        while i < len(items):
            score = items[i][1]
            same_rank = [items[i][0]]

            j = i + 1
            while j < len(items) and items[j][1] == score:
                same_rank.append(items[j][0])
                j += 1

            for name in same_rank:
                msg += str(rank) + ". " + name + " : " + str(score) + "\n"

            rank += len(same_rank)
            i = j

        return msg

    def disconnect_all_clients_server_end(self):
        # end connections but keep server socket open for new clients
        for client_socket in list(self.clients.keys()):
            try:
                client_socket.send("GAME OVER\n".encode())
                client_socket.close()
            except (socket.error, OSError):
                pass

        self.clients.clear()
        self.num_of_clients = 0
        self.scores.clear()

    def end_game_normal(self):
        # send final ranked scoreboard and winner message
        final_msg = self.final_ranked_scoreboard()
        self.add_message_to_text(final_msg.strip())
        self.broadcast(final_msg)

        max_score = -1
        for name in self.scores:
            if self.scores[name] > max_score:
                max_score = self.scores[name]

        winners = []
        for name in self.scores:
            if self.scores[name] == max_score:
                winners.append(name)

        winner_msg = "WINNER(S): " + ", ".join(winners) + "\n"
        self.add_message_to_text(winner_msg.strip())
        self.broadcast(winner_msg)

        # finish game and allow new games later
        self.game_started = False
        self.waiting_for_answers = False
        self.start_button.config(text="Start Game")

        self.add_message_to_text("--- Game finished ---")
        self.broadcast("--- Game finished ---")
        self.disconnect_all_clients_server_end()

    def end_game_not_enough_players(self):
        # end game if fewer than 2 players remain connected
        self.game_started = False
        self.waiting_for_answers = False
        self.start_button.config(text="Start Game")

        msg = "Game ended because there are less than 2 players remaining"
        self.add_message_to_text(msg)
        self.broadcast(msg)
        self.disconnect_all_clients_server_end()

    def give_questions(self):
        # stop if there are no questions loaded
        if len(self.questions_list) == 0:
            return

        x = 0
        while self.game_started and x < self.num_questions_to_ask:
            # end game if number of clients is less than 2
            if self.num_of_clients < 2:
                self.end_game_not_enough_players()
                return

            # if num of questions entered in the gui is more than the questions in the file, reuse the same questions from the beginning
            q = self.questions_list[x % len(self.questions_list)]

            self.expected_players = list(self.clients.values())
            self.answers = {}
            self.answer_order = []
            self.waiting_for_answers = True
            self.end_after_current_question = False

            # broadcast question to all players
            question_msg = (
                "\n" + "QUESTION\n"
                + q["question"] + "\n"
                + q["A"] + "\n"
                + q["B"] + "\n"
                + q["C"] + "\n" + "\n"
            )

            self.add_message_to_text(question_msg.strip())
            self.broadcast(question_msg)

            # wait until all remaining expected players answered
            while self.game_started and len(self.answers) < len(self.expected_players):
                # keep going until the current question finishes
                if self.num_of_clients < 2:
                    self.end_after_current_question = True
                time.sleep(0.1)

            self.waiting_for_answers = False

            if not self.game_started:
                return

            # read correct answer letter from question data
            correct_letter = q["correct"].strip().upper()

            # find the first player who answered correctly
            first_correct_name = ""
            i = 0
            while i < len(self.answer_order):
                nm = self.answer_order[i]
                if nm in self.answers:
                    if self.answers[nm].strip().upper() == correct_letter:
                        first_correct_name = nm
                        i = len(self.answer_order)
                    else:
                        i += 1
                else:
                    i += 1

            # compute points for this question
            round_points = {}
            for nm in self.expected_players:
                round_points[nm] = 0

            for nm in self.expected_players:
                if nm in self.answers:
                    if self.answers[nm].strip().upper() == correct_letter:
                        round_points[nm] = 1

            # add bonus points to the palyer that gets the correct answer first
            if first_correct_name != "":
                extra = len(self.expected_players) - 1
                if extra < 0:
                    extra = 0
                round_points[first_correct_name] = round_points[first_correct_name] + extra

            # update the server scoreboard
            for nm in self.expected_players:
                if nm not in self.scores:
                    self.scores[nm] = 0
                self.scores[nm] = self.scores[nm] + round_points[nm]

            scoreboard_msg = self.build_scoreboard_message()

            # send a private result message to each connected client
            for client_socket in list(self.clients.keys()):
                name = self.clients[client_socket]

                chosen = ""
                if name in self.answers:
                    chosen = self.answers[name].strip().upper()

                got = 0
                if name in round_points:
                    got = round_points[name]

        
                if chosen == correct_letter:
                    if name == first_correct_name and (len(self.expected_players) - 1) > 0:
                        private_msg = (
                            "RESULT\n"
                            + "You chose " + chosen + "\n"
                            + "Your answer is correct and first\n"
                            + "Correct answer: " + correct_letter + "\n"
                            + "Points received: " + str(got) + "\n" + "\n"
                            + scoreboard_msg
                        )
                    else:
                        private_msg = (
                            "RESULT\n"
                            + "You chose " + chosen + "\n"
                            + "Your answer is correct\n"
                            + "Correct answer: " + correct_letter + "\n"
                            + "Points received: " + str(got) + "\n" + "\n"
                            + scoreboard_msg
                        )
                else:
                    private_msg = (
                        "RESULT\n"
                        + "You chose " + chosen + "\n"
                        + "Your answer is wrong\n"
                        + "Correct answer: " + correct_letter + "\n"
                        + "Points received: 0\n" + "\n"
                        + scoreboard_msg
                    )

                try:
                    client_socket.send(private_msg.encode())
                except (socket.error, OSError):
                    self.remove_client(client_socket)

            # broadcast correct answer and scoreboard to everyone
            correct_msg = "CORRECT\n" + correct_letter + "\n"
            self.add_message_to_text(correct_msg.strip())
            self.broadcast(correct_msg)

            self.add_message_to_text(scoreboard_msg.strip())
            self.broadcast(scoreboard_msg)

            x += 1

            # end game after finishing this question if needed
            if self.end_after_current_question:
                self.end_game_not_enough_players()
                return

        if self.game_started:
            self.end_game_normal()

    def get_questions(self, filename):
        # open the file for the questions and give error if it fails
        try:
            f = open(filename, "r", encoding="utf-8")
        except OSError:
            messagebox.showerror("Error", "Question file could not be opened")
            return None

        # read all lines and remove newline characters
        lines = []
        for line in f:
            lines.append(line.rstrip("\n"))
        f.close()

        # parse questions in groups of 5 lines
        # 5 lines for each question -> one for question, three for choices and one for correct answer
        questions = []
        i = 0
        while i + 4 < len(lines):
            question_text = lines[i].strip()
            choice_a = lines[i + 1].strip()
            choice_b = lines[i + 2].strip()
            choice_c = lines[i + 3].strip()

            answer_line = lines[i + 4].strip().upper()
            if ":" in answer_line:
                correct = answer_line.split(":")[-1].strip()
            else:
                correct = answer_line

            questions.append({
                "question": question_text,
                "A": choice_a,
                "B": choice_b,
                "C": choice_c,
                "correct": correct
            })

            i += 5

        return questions

    def get_filename(self):
        # get filename from the server gui and check its validity
        filename = self.file_entry.get().strip()
        if not filename:
            messagebox.showerror("Error", "Please enter the file name.")
            return None
        if not filename.lower().endswith(".txt"):
            messagebox.showerror("Error", "Please enter a valid file name.")
            return None
        return filename

    def start_listening(self):
        port_str = self.port_entry.get()
        if not port_str:
            messagebox.showerror("Error", "Please enter a port number.")
            return

        try:
            port = int(port_str)
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind(('127.0.0.1', port))
            self.server_socket.listen(5)

            self.is_listening = True
            self.listen_button.config(text="Stop Listening")
            self.add_message_to_text(f"--- Server listening on port {port} ---")

            self.thread = threading.Thread(target=self.accept_connections, daemon=True)
            self.thread.start()

            self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        except (socket.error, ValueError) as e:
            messagebox.showerror("Server Error", f"Could not start server: {e}")
            self.is_listening = False
            if self.server_socket:
                self.server_socket.close()

    def stop_listening(self):
        # stop server and disconnect all clients
        if self.is_listening:
            self.is_listening = False
            for client_socket in list(self.clients.keys()):
                self.remove_client(client_socket)

            self.server_socket.close()
            self.listen_button.config(text="Listen")
            self.add_message_to_text("--- Server stopped ---")

    def accept_connections(self):
        # accept clients until server stops listening
        while self.is_listening:
            try:
                client_socket, client_address = self.server_socket.accept()
                name = client_socket.recv(1024).decode().strip()

                # cannot reconnect if they disconnected during a game
                if name in self.disconnected_names:
                    try:
                        client_socket.send("You cannot reconnect.\n".encode())
                    except (socket.error, OSError):
                        pass
                    client_socket.close()
                    self.add_message_to_text(f"Rejected reconnect attempt for '{name}'")
                    continue

                # only allow unique names and block new clients after the game has already strated
                if name not in self.clients.values() and self.game_started == False:
                    self.clients[client_socket] = name
                    self.add_message_to_text(f"New connection from {client_address[0]} as '{name}'")
                    self.broadcast(f"'{name}' has joined the chat.")

                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, name), daemon=True)
                    client_thread.start()
                    self.num_of_clients += 1
                else:
                    client_socket.send("Cannot have the same name as another player".encode())
                    client_socket.close()
                    self.add_message_to_text(f"Someone tried to join the server with the already existing name '{name}' and have been disconnected")

            except (socket.error, OSError):
                break

    def handle_client(self, client_socket, name):
        # read messages from a single client
        while self.is_listening:
            try:
                message = client_socket.recv(1024).decode()
                if message:
                    message = message.strip()
                    upper_message = message.upper()

                    # messages as quiz answers during answering phase
                    if self.game_started and self.waiting_for_answers:
                        if name in self.expected_players and name not in self.answers:
                            if upper_message == "A" or upper_message == "B" or upper_message == "C":
                                self.answers[name] = upper_message
                                self.answer_order.append(name)
                            else:
                                try:
                                    client_socket.send("Please answer with A, B, or C.".encode())
                                except (socket.error, OSError):
                                    pass
                        continue

                    self.add_message_to_text(f"'{name}': {message}")
                    self.broadcast(f"'{name}': {message}", sender_socket=client_socket)
                else:
                    self.remove_client(client_socket)
                    break
            except (socket.error, OSError):
                self.remove_client(client_socket)
                break

    def broadcast(self, message, sender_socket=None):
        for client_socket in list(self.clients.keys()):
            try:
                client_socket.send(message.encode())
            except (socket.error, OSError):
                self.remove_client(client_socket)

    def remove_client(self, client_socket):
        # remove a client and notify everyone
        if client_socket in self.clients:
            name = self.clients[client_socket]

            # mark cannot reconnect if they disconnected during a game
            if self.game_started:
                if name not in self.disconnected_names:
                    self.disconnected_names.append(name)

            try:
                client_socket.close()
                self.clients.pop(client_socket)
                self.num_of_clients -= 1
            except (socket.error, OSError):
                pass

            disconnect_msg = "'" + name + "' has disconnected."
            self.add_message_to_text(disconnect_msg)
            self.broadcast(disconnect_msg)

            left_msg = "'" + name + "' has left the chat."
            self.broadcast(left_msg)

            # disconnect during answering
            if self.game_started and self.waiting_for_answers:
                if name in self.expected_players:
                    try:
                        self.expected_players.remove(name)
                    except ValueError:
                        pass

            # end game if there are less than 2 players while not answering questions
            if self.game_started and (not self.waiting_for_answers) and self.num_of_clients < 2:
                self.end_game_not_enough_players()

    def add_message_to_text(self, message):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, message + "\n")
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.yview(tk.END)

    def on_closing(self):
        if self.is_listening:
            self.stop_listening()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatServer(root)
    root.mainloop()
