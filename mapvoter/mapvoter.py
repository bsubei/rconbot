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
# A class that handles map voting mechanics to be used by a Squad RCON client.
#

import argparse
import collections
import time
import logging
import re

from srcds import rcon
import squad_map_randomizer

logger = logging.getLogger(__name__)


# Wait 15 minutes before starting a map vote at the beginning of every map.
DEFAULT_VOTING_DELAY_S = 60 * 15

# The string to be formatted and sent to the server when a mapvote starts.
START_VOTE_MESSAGE_TEMPLATE = (
    'Please cast a vote for the next map by typing the corresponding number in AllChat.\n{candidate_maps}')
# The string to be formatted and sent to the server when a mapvote is over.
VOTE_RESULT_MESSAGE_TEMPLATE = 'The map with the most votes is: {} with {} votes!'

# How long to listen to chat for vote casts in seconds.
DEFAULT_VOTING_TIME_DURATION_S = 30.0

# The default port for RCON.
DEFAULT_PORT = 21114

# TODO(bsubei): pull this in as a Python package and use it.
# The default URL to use to fetch the Squad map layers.
DEFAULT_LAYERS_URL = 'https://raw.githubusercontent.com/bsubei/squad_map_layers/master/layers.json'

# How long to sleep in between each "has the map changed" check (in seconds).
SLEEP_BETWEEN_MAP_CHECKS_S = 5.0


# TODO weird that so much state (getting chat then clearing it) is in here
def is_player_asking_for_mapvote(player_messages):
    # Fetch the player chat since we last checked.
    for player_id, messages in player_messages.items():
        for message in messages:
            if '!mapvote' in message:
                return True
    return False


def get_rotation_from_filepath(map_rotation_filepath):
    """
    Given the filepath to the map rotations file, return the list of map rotations. The file should list each map on a
    separate line.
    """
    # Fetches the map rotation from the given .txt file and returns it as a
    # list of strings (with newlines removed).
    with open(map_rotation_filepath, 'r') as f:
        return list(filter(None, [line.strip('\n') for line in f.readlines()]))


def format_candidate_maps(candidate_maps):
    """ Returns a formatted string of all the candidate maps to be displayed to players in chat. """
    return '\n'.join([f'{index}) {candidate}' for index, candidate in enumerate(candidate_maps)])


def get_highest_map_vote(candidate_maps, player_messages):
    """
    Given a list of candidate maps and player messages (dict of player_id -> list(messages)), return both the key
    and count for the highest map vote.

    NOTE: ties are broken by choosing the map first encountered (first voted on) in the given candidate maps list.

    :param candidate_maps: list(str) The list of candidate maps that are being voted on.
    :param player_messages: dict(str->list(str)) Contains the list of messages for each player (keyed by player_id).
    :return: tuple(str, int) The name of the winning map and the vote count it received. None if there are no votes.
    """
    # This is a counter that keeps track of the count for each map (key).
    map_votes = collections.Counter()

    # Go over every message and count it towards a map if you can use it as an
    # index. Otherwise, skip it.
    for player_id, messages in player_messages.items():
        if isinstance(messages, str):
            raise ValueError(
                'Given list of messages is just a string, not a list!')

        # In order to avoid double-counting votes from a single voter, use their most recent valid vote and throw away
        # the rest of their votes.
        for message in reversed(messages):
            try:
                # Grab the last word in the message and consider that the vote.
                vote_message = re.search(r'\w+$', message.strip()).group(0)
                map_votes.update([candidate_maps[int(vote_message)]])
                # If we count this message as a vote, ignore the previous messages from this player (so we don't double
                # count votes for this player).
                break
            except (ValueError, IndexError, AttributeError):
                logger.warning(f'Player with id {player_id} entered invalid mapvote message {message}. Skipping...')

    return map_votes.most_common(1)[0] if map_votes else None


class MapVoter:
    """
    Instantiate this class and use it to send map voting instructions and listen to player responses (blocking).
    Whenever a new map starts, call reset_new_map() and you can then poll should_start_map_vote() and then call
    start_map_vote() when it's ready.
    """

    def __init__(self, squad_rcon_client,
                 voting_delay_s=DEFAULT_VOTING_DELAY_S, voting_time_duration_s=DEFAULT_VOTING_TIME_DURATION_S):
        """
        The constructor for MapVoter.

        :param squad_rcon_client: RconConnection The handle to the rcon client.
        :param voting_time_duration_s: float The duration of time to wait for players to vote on maps in seconds.
        """
        # This stores the handle to the squad_rcon_client (so we can contact the squad server).
        self.squad_rcon_client = squad_rcon_client

        # How many seconds to wait for players to vote on a map.
        self.voting_time_duration_s = voting_time_duration_s

        # How many seconds to wait after map start to vote on a new map.
        self.voting_delay_s = voting_delay_s

        # Since we just started, pretend we reset to a new map. This sets self.time_map_started to time now.
        self.reset_new_map()

    def reset_new_map(self):
        """ This function should be called any time the map is reset, in order to reset time since map started. """
        # This stores the time when the latest map started (since the epoch).
        self.time_map_started = time.time()
        self.has_voted_on_this_map = False

    def get_duration_since_map_started(self):
        """ Returns the duration of time (in seconds) since the map started. """
        return time.time() - self.time_map_started

    def get_duration_until_map_vote(self):
        """
        Return the duration (in seconds) until the map vote. A positive value means there is still time left until map
        vote, and a zero or negative value means map vote should start or has started already.
        """
        return self.voting_delay_s - self.get_duration_since_map_started()

    # TODO all this API needs cleanup
    def should_start_map_vote(self, player_messages):
        """
        If the duration until map vote is zero or less, and we haven't voted on this map before, then return True.
        Otherwise, return False.
        """
        return (self.get_duration_until_map_vote() <= 0 and
                not self.has_voted_on_this_map and
                is_player_asking_for_mapvote(player_messages))

    def listen_to_votes(self, sleep_duration_s, halftime_message=None):
        """
        Listen to the chat messages simply by waiting and then sending a broadcast message (which flushes any pending
        chat messages that arrived while we waited).
        NOTE: this blocks for sleep_duration_s seconds!

        :param sleep_duration_s: float The duration of time to listen to chat messages.
        :param halftime_message: str The message to broadcast after half the duration.
        """
        # Send out a reminder message halfway through voting, but only once.
        time.sleep(sleep_duration_s / 2)
        if halftime_message:
            self.squad_rcon_client.exec_command(f'AdminBroadcast {halftime_message}')

        time.sleep(sleep_duration_s / 2)

        # We're done listening. Send a broadcast that voting is done (so it flushes all the chat messages).
        self.squad_rcon_client.exec_command(f'AdminBroadcast Voting is over!')

    def start_map_vote(self, candidate_maps):
        """ Starts a map vote by sending candidate maps message and listening to chat for a specified duration. """
        # Mark the flag that we've voted on this map so we don't vote again.
        self.has_voted_on_this_map = True

        # Get the list of map candidates (randomly chosen from the rotation).
        candidate_maps_formatted = format_candidate_maps(candidate_maps)
        logger.info(f'Starting a new map vote! Candidate maps:\n{candidate_maps_formatted}')

        # Send mapvote message (includes list of candidates).
        start_vote_message = START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=candidate_maps_formatted)
        self.squad_rcon_client.exec_command(f'AdminBroadcast {start_vote_message}')

        # Clear the old player chat messages that might have accumulated before the vote started.
        self.squad_rcon_client.clear_player_chat()

        # Listen to the chat messages and collect them all as a dict of player_id -> list(str) where each player could
        # have posted a list of messages.
        self.listen_to_votes(self.voting_time_duration_s, start_vote_message)
        player_messages = self.squad_rcon_client.get_parsed_player_chat()
        logger.debug(f'The received player messages were:\n{player_messages}')

        # Parse the chat messages into votes, and choose the map with the highest votes.
        result = get_highest_map_vote(
            candidate_maps, player_messages)
        if result:
            # If the voting was valid, send a message with the results, then set next map.
            winner_map, vote_count = result
            vote_result_message = VOTE_RESULT_MESSAGE_TEMPLATE.format(
                winner_map, vote_count)
            self.squad_rcon_client.exec_command(f'AdminBroadcast {vote_result_message}')
            logger.info(vote_result_message)
            self.squad_rcon_client.exec_command(f'AdminSetNextMap "{winner_map}"')
        else:
            # Else, send a message saying voting failed and reset so it starts the vote again later.
            vote_failed_message = 'The map vote failed!'
            self.squad_rcon_client.exec_command(f'AdminBroadcast {vote_failed_message}')
            logger.warning(vote_failed_message)
            self.reset_new_map()

    # TODO have it also return next map
    def get_current_map(self):
        """ Returns the current map by querying the RCON server and parsing the response using regex. """
        response = self.squad_rcon_client.exec_command('ShowNextMap')
        try:
            return re.search(r'Current map is (.+),', response).group(1)
        except AttributeError:
            logger.error('Failed to parse ShowNextMap.')
            return None


def parse_cli():
    """ Parses sys.argv (commandline args) and returns a parser with the arguments. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--rcon-address', required=True, help='The address to the RCON server (IP or URL).')
    parser.add_argument('--rcon-port', type=int, help=f'The port for the RCON server. Defaults to {DEFAULT_PORT}.',
                        default=DEFAULT_PORT)
    parser.add_argument('--rcon-password', required=True, help='The password for the RCON server.')
    parser.add_argument('--voting-delay', type=float,
                        help=('How long to wait (in seconds) after map start before voting. Defaults to '
                              f'{DEFAULT_VOTING_DELAY_S}.'), default=DEFAULT_VOTING_DELAY_S)
    parser.add_argument('--voting-duration', type=float,
                        help=f'How long to listen for votes in seconds. Defaults to {DEFAULT_VOTING_TIME_DURATION_S}.',
                        default=DEFAULT_VOTING_TIME_DURATION_S)
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                        help='Verbose flag to indicate that DEBUG level output should be logged')
    return parser.parse_args()


def setup_logger(verbose):
    """ Sets up the logger based on the verbosity level. """
    level = logging.DEBUG if verbose else logging.INFO

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    ch.setLevel(level)

    logger.setLevel(level)
    logger.addHandler(ch)


def main():
    """ Run the Map Voter script. """
    print('Starting up mapvoter script!')
    args = parse_cli()

    # Set up the logger.
    setup_logger(args.verbose)

    try:
        # Set up the connection to RCON and initialize the mapvoter.
        conn = rcon.RconConnection(args.rcon_address, port=args.rcon_port, password=args.rcon_password)
        mapvoter = MapVoter(conn, args.voting_delay, args.voting_duration)

        logger.info(f'Will start polling for new map every {SLEEP_BETWEEN_MAP_CHECKS_S} seconds and waiting to start a '
                    'map vote...')

        # Get the current map at start so we know when the map changes.
        current_map = mapvoter.get_current_map()

        # Spin until we're done, but do it slowly.
        while True:
            # Check if we started a new map, and reset the mapvoter timer if it did.
            possibly_new_map = mapvoter.get_current_map()
            logger.debug(f'Current map: {current_map}, just checked map: {possibly_new_map}')

            # Print out how long until or since map vote.
            if mapvoter.get_duration_until_map_vote() > 0:
                logger.debug(f'Time until map vote: {mapvoter.get_duration_until_map_vote()}')
            else:
                logger.debug(f'Time since map vote: {-mapvoter.get_duration_until_map_vote()}')

            # If you detect a map change, reset the vote.
            if current_map != possibly_new_map:
                current_map = possibly_new_map
                mapvoter.reset_new_map()
                logger.info('Map change detected! Resetting mapvoter!')

            # TODO get most recent player messages
            player_messages = mapvoter.squad_rcon_client.get_parsed_player_chat()
            mapvoter.squad_rcon_client.clear_player_chat()

            # If it's time to vote, start the vote!
            if mapvoter.should_start_map_vote(player_messages):
                NO_FILEPATH = None
                layers = squad_map_randomizer.get_json_layers(NO_FILEPATH, DEFAULT_LAYERS_URL)
                candidate_maps = squad_map_randomizer.get_map_rotation(
                    layers, num_starting_skirmish_maps=1, num_repeating_pattern=1)
                mapvoter.start_map_vote(squad_map_randomizer.get_layers(candidate_maps))

            time.sleep(SLEEP_BETWEEN_MAP_CHECKS_S)
    finally:
        # No matter what happens, close the damn socket when we're done or the squad server might hang!
        # TODO use a context manager in the rcon client to automatically close and then we can use a 'with' clause.
        conn._sock.close()


if __name__ == '__main__':
    main()
