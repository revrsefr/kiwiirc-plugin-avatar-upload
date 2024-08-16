import irc.bot
import logging
import threading
import os
import signal
import sys
import time
import sqlite3
from jaraco.stream import buffer

# IRC Bot configuration
IRC_SERVER = 'irc.chateagratis.chat'
IRC_PORT = 6667
IRC_CHANNEL_OPERS = '#opers'  # Channel where the bot should ignore messages
IRC_NICKNAME = 'FilesControl'
PID_FILE = 'irc_bot.pid'
MESSAGE_FILE = 'irc_messages.txt'  # File to store messages
LOG_DIR = './logs'
LOG_FILE = os.path.join(LOG_DIR, 'bot.log')
DB_FILE = 'ignored_nicks.db'

# Ensure the log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configure logging to write to a file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Custom buffer class to ignore decoding errors
class IgnoreErrorsBuffer(buffer.DecodingLineBuffer):
    def handle_exception(self):
        pass

# Assign the custom buffer class to the ServerConnection
irc.client.ServerConnection.buffer_class = IgnoreErrorsBuffer

class ReportBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel_opers, nickname, server, port=6667):
        super().__init__([(server, port)], nickname, nickname)
        self.channel_opers = channel_opers
        self.is_connected = False
        self.connection_event = threading.Event()

    def on_welcome(self, connection, event):
        logging.info("Connected to IRC server")
        connection.join(self.channel_opers)
        logging.info(f"Joining channel {self.channel_opers}")

    def on_join(self, connection, event):
        if event.target == self.channel_opers:
            logging.info(f"Successfully joined channel {self.channel_opers}")
            self.is_connected = True
            self.connection_event.set()

    def on_ping(self, connection, event):
        """Handle ping events."""
        logging.debug("Received ping from server")
        connection.pong(event.target)
        logging.debug("Responded to ping")

    def on_pubmsg(self, connection, event):
        """Ignore all public messages from the #opers channel."""
        try:
            channel = event.target
            nickname = irc.client.NickMask(event.source).nick

            # If the message is from #opers, ignore it
            if channel == self.channel_opers:
                logging.debug(f"Ignoring message from {nickname} in {channel}")
                return

            # If needed, handle messages from other channels
            message = event.arguments[0]
            logging.info(f"Received message from {nickname} in {channel}: {message}")

        except Exception as e:
            logging.error(f"Error while processing channel message: {e}")

    def send_report(self, message, account=None):
        if self.is_connected:
            try:
                logging.info(f"Sending message to {self.channel_opers}: {message}")
                self.connection.privmsg(self.channel_opers, message)
                logging.info("Message sent successfully")

                if account:
                    notice_message = (
                        "Ha sido reportado a los operadores. "
                        "No INTENTES subir nuevamente este tipo de foto/imagen o serás baneado permanentemente del chat."
                    )
                    self.send_notice(account, notice_message)
            except Exception as e:
                logging.error(f"Failed to send message: {e}")
        else:
            logging.warning("Bot is not connected to IRC channel, message not sent.")

    def send_notice(self, account, notice_message):
        """Send a private notice to the user."""
        if account:
            try:
                logging.info(f"Sending notice to {account}: {notice_message}")
                self.connection.notice(account, notice_message)
                logging.info("Notice sent successfully")
            except Exception as e:
                logging.error(f"Failed to send notice to {account}: {e}")
        else:
            logging.error("No account name provided for sending notice.")

    def check_for_messages(self):
        while True:
            if os.path.exists(MESSAGE_FILE):
                with open(MESSAGE_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                    messages = f.readlines()

                if messages:
                    for message in messages:
                        message = message.strip()
                        logging.debug(f"Processing message: {message}")

                        if "REPORTE:" in message:
                            account_start = message.find("-->") + 3
                            account_end = message.find("<--")
                            if account_start > 3 and account_end > account_start:
                                account = message[account_start:account_end].strip()
                                logging.debug(f"Extracted account name: {account}")
                                self.send_report(message, account)
                            else:
                                logging.error(f"Failed to extract account name from message: {message}")
                                self.send_report(message)
                        else:
                            self.send_report(message)

                with open(MESSAGE_FILE, 'w'):
                    pass
            time.sleep(1)  # Check every second for new messages

    def is_admin(self, nickname):
        # Define your admin list here or fetch it from a config/database
        admins = ["reverse", "JeFeCiTo"]  # Replace with actual admin nicknames
        return nickname in admins

def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS ignored_nicks
                      (nick TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

def add_ignored_nick(nick):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO ignored_nicks (nick) VALUES (?)', (nick,))
    conn.commit()
    conn.close()

def is_nick_ignored(nick):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM ignored_nicks WHERE nick = ?', (nick,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def write_pid_file():
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    logging.info(f"PID file created: {PID_FILE}")

def remove_pid_file():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        logging.info(f"PID file removed: {PID_FILE}")

def check_existing_bot():
    if os.path.exists(PID_FILE):
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        try:
            os.kill(pid, 0)
            logging.error(f"Bot is already running with PID {pid}. Exiting.")
            sys.exit(1)
        except OSError:
            logging.warning(f"Stale PID file found, no process with PID {pid}. Removing.")
            remove_pid_file()

def run_bot():
    check_existing_bot()
    write_pid_file()

    bot = ReportBot(IRC_CHANNEL_OPERS, IRC_NICKNAME, IRC_SERVER, IRC_PORT)
    bot_thread = threading.Thread(target=bot.start)
    bot_thread.start()

    def cleanup(signum, frame):
        logging.info(f"Signal {signum} received, shutting down bot.")
        remove_pid_file()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    message_check_thread = threading.Thread(target=bot.check_for_messages)
    message_check_thread.start()

    return bot

if __name__ == "__main__":
    setup_database()
    run_bot()

    while True:
        time.sleep(1)
