from telnetserver import TelnetServer
import subprocess
import os
import time
from utils.logger import Logger
import json
import logging
import random

server = TelnetServer(port=1234)
proc = subprocess.Popen(['/suchai-2-software/build-gnd/apps/groundstation/ground-app'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.STDOUT)
os.set_blocking(proc.stdout.fileno(), False)
os.set_blocking(proc.stdin.fileno(), False)

RADIO_DELAY_SECONDS = float(os.environ.get("RADIO_DELAY_SECONDS", "3"))
DELAY_TRIGGER_SUBSTRING = os.environ.get("DELAY_TRIGGER_SUBSTRING", "1: ") # the delay should be triggered only when a command is being sent to the satellite but not to the ground.


banner = '\nWelcome to the Ground Station Terminal\n\n'
banner = banner + '\n'
banner = banner + '* * * * * * * * * * W A R N I N G * * * * * * * * * *\n'
banner = banner + 'This computer system is for authorized use only.'
banner = banner + ' Unauthorized or improper use of this system may result in administrative disciplinary action, civil charges or criminal penalties, and other sanctions.'
banner = banner + ' By continuing to use this system you indicate your awareness of and consent to these terms and conditions of use.\n\n'
banner = banner + '* * * * * * * * * * * * * * * * * * * * * * * * * * *\n'
banner = banner + 'Type "activate" to activate this terminal.\n'

second_banner = 'Terminal enabled\n\n'
second_banner = second_banner + '\nWelcome to the Ground Station Terminal\n\n'
second_banner = second_banner + 'Command not found: □ \n'
second_banner = second_banner + 'Use "help" to see the list of available commands\n'


clients = []
pre_auth_clients = []

# The below code enables multiple clients to interact with the same ground-app instance.
# All connected clients can send commands to the group-app after they typed the ACTIVATE.
# All connected clients will receive each others' results sent by the ground-app.
# If there are multiple clients connected, the first one to send a command and hit enter, sends it first.

while True:
    time.sleep(0.01)
    server.update()

    # For each newly connected client
    for new_client in server.get_new_clients():
        pre_auth_clients.append(new_client)
        server.send_message(new_client, banner)

    for disconnected_client in server.get_disconnected_clients():
        if disconnected_client in clients:
            clients.remove(disconnected_client)
        elif disconnected_client in pre_auth_clients:
            pre_auth_clients.remove(disconnected_client)

    # For each message a client has sent
    for sender_client, message in server.get_messages():
        if sender_client in clients:
            if DELAY_TRIGGER_SUBSTRING in message:
                jitter = random.uniform(-0.5, 0.5) # add some random noise every time
                delay = max(0, RADIO_DELAY_SECONDS + jitter)
                print(f"[Telnet] Simulating radio delay of {delay:.2f}s for command: {message}")
                time.sleep(delay)
            proc.stdin.write((message + '\n').encode('utf-8', 'backslashreplace'))
            proc.stdin.flush()
            Logger.write_data(
                _class_name = 'TelnetMessageRecieved',
                _id = hash('TelnetMessageRecieved'),
                _data = json.dumps({'message': message, 'remote_client_id:': sender_client}),
                _log_type = logging.INFO
            )

        elif sender_client in pre_auth_clients:
            if message == 'activate':
                pre_auth_clients.remove(sender_client)
                clients.append(sender_client)
                server.send_message(sender_client, second_banner)
                Logger.write_data(
                    _class_name = 'TelnetTerminalActivated',
                    _id = hash('TelnetTerminalActivated'),
                    _data = json.dumps({'remote_client_id:': sender_client}),
                    _log_type = logging.INFO
                )
            else:
                server.send_message(sender_client, 'Type "activate" to activate this terminal.\n')

    outs = proc.stdout.read()
    if outs:
        print(outs.decode('utf-8', 'backslashreplace'))
        Logger.write_data(
            _class_name = 'GSTerminalOutput',
            _id = hash('GSTerminalOutput'),
            _data = json.dumps({'message': outs.decode('utf-8', 'backslashreplace')}),
            _log_type = logging.INFO
        )
        for client in clients:
            server.send_message(client, outs.decode('utf-8', 'backslashreplace'))
