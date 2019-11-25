#! /usr/bin/env python3

# Copyright (C) 2019 Basheer Subei
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
#
# A class that communicates with a Squad server using RCON. Uses a slightly modified pysrcds underneath.
#

from srcds import rcon
import logging
import multiprocessing
import re
import time

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def gather_squad_chat(conn, queue):
    # Keep listening to messages, and add them to the queue if they're chat messages.
    import srcds
    while True:
        response = conn._recv_pkt()
        if response.pkt_type == srcds.rcon.SQUAD_CHAT_STREAM:
            queue.put(response.body)


class SquadRCONClient:
    """
    TODO
    """

    def __init__(self, server_address, server_password):
        """
        The constructor for SquadRCONClient.

        :param server_address: tuple(str, int) The IP and port of the server to connect. e.g. ('0.0.0.0', 1234)
        :param server_password: str The RCON password to use to connect to the server.
        """
        self.rcon = rcon.RconConnection(server_address[0], port=server_address[1], password=server_password, single_packet_mode=True)

    def send_admin_message(self, message):
        """ Sends an admin broadcast message to the server. """
        self.rcon.exec_command('AdminBroadcast "{}"'.format(message))

    def listen_to_allchat_for_duration(self, duration_s, reminder_message=None):
        """
        Listen to the chat messages and collect them all as a dict of player_id -> list(str) where each player could
        have posted a list of messages.
        NOTE: the list of player messages is given in chronological order.
        NOTE: this blocks for duration_s seconds!

        :param duration_s: float The duration of time to listen to chat messages before returning.
        :return: dict(str: list(str)) The player messages as a dict of player_id -> list(string messages)
        """
        player_messages = {}

        q = multiprocessing.Queue()
        p = multiprocessing.Process(target=gather_squad_chat, args=(self.rcon, q))

        # Until time runs out, keep collecting player messages from chat.
        p.start()
        time_started = time.time()
        # Spin until we're done, but do it slowly.
        while time.time() - time_started < duration_s:
            time.sleep(0.5)
            # TODO this doesn't work since the only connection intercepts all recv in gather_squad_chat
            ## Send out a reminder message halfway through voting, but only once.
            #if reminder_message and time.time() - time_started < (duration_s / 2.0):
            #    self.send_admin_message(reminder_message)
            #    reminder_message = None
        # We're done listening. Just kill the chat listener process.
        p.terminate()

        STEAM_ID_PATTERN = r'\[SteamID:(\w*)\]'
        while not q.empty():
            # TODO catch any regex fails and continue
            text = q.get().decode('utf-8').strip('\x00')
            player_id = re.search(STEAM_ID_PATTERN, text).group(1)
            if player_id in player_messages:
                player_messages[player_id].append(text)
            else:
                player_messages.update({player_id: [text]})
        return player_messages

    def set_next_map(self, next_map):
        """ Call the set next map command on the server. """
        # self.rcon.exec_command('AdminBroadcast setting next map to "{}"'.format(next_map))
        self.rcon.exec_command('AdminSetNextMap "{}"'.format(next_map))

    # TODO have it also return next map
    def get_current_map(self):
        response = self.rcon.exec_command('ShowNextMap')
        try:
            return re.search(r'Current map is (.+),', response.decode('utf-8')).group(1)
        except AttributeError:
            logger.error('Failed to parse ShowNextMap.')
            return None
