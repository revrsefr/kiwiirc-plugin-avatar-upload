import irc.bot
import logging
import threading
import os
import signal
import sys
import time

# IRC Bot configuration
IRC_SERVER = 'irc.chateagratis.chat'
IRC_PORT = 6667
IRC_CHANNEL_OPERS = '#opers'  # Channel where the report is sent
IRC_NICKNAME = 'FilesControl'
PID_FILE = 'irc_bot.pid'
MESSAGE_FILE = 'irc_messages.txt'  # File to store messages

class ReportBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel_opers, nickname, server, port=6667):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
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
        """Explicitly handle ping events."""
        logging.debug("Received ping from server")
        connection.pong(event.target)
        logging.debug("Responded to ping")

    def send_report(self, message, account=None):
        if self.is_connected:
            try:
                logging.info(f"Sending message to {self.channel_opers}: {message}")
                self.connection.privmsg(self.channel_opers, message)
                logging.info("Message sent successfully")

                # Send a notice to the user who uploaded the inappropriate content
                if account:
                    notice_message = (
                        "You have been reported to the operators. "
                        "Do not TRY TO UPLOAD THIS KIND OF PICTURES or you will be permanently banned."
                    )
                    self.send_notice(account, notice_message)
            except Exception as e:
                logging.error(f"Failed to send message: {e}")
        else:
            logging.warning("Bot is not connected to IRC channel, message not sent.")

    def send_notice(self, account, notice_message):
        """Send a private notice to the user."""
        if account:  # Ensure that account is not empty
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
                with open(MESSAGE_FILE, 'r') as f:
                    messages = f.readlines()

                if messages:
                    for message in messages:
                        message = message.strip()
                        logging.debug(f"Processing message: {message}")

                        if "REPORTE:" in message:
                            # Attempt to extract the account name
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
                            # Send the second message directly
                            self.send_report(message)

                # Clear the file after processing messages
                with open(MESSAGE_FILE, 'w'):
                    pass
            time.sleep(1)  # Check every second for new messages

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
    logging.basicConfig(level=logging.DEBUG)
    run_bot()

    while True:
        time.sleep(1)
