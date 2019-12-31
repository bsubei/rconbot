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
# A class and script that handles map voting mechanics to be used by a Squad RCON client.
#

import argparse
import collections
import time
import logging
import random
import re

from srcds import rcon
import squad_map_randomizer

logger = logging.getLogger(__name__)


# Wait this long in between map votes.
DEFAULT_VOTING_COOLDOWN_S = 60 * 30

# The string to be formatted and sent to the server when a map vote starts.
START_VOTE_MESSAGE_TEMPLATE = (
    'Please cast a vote for the next map by typing the corresponding number in AllChat.\n{candidate_maps}')
# The string to be formatted and sent to the server when a map vote is over.
VOTE_RESULT_MESSAGE_TEMPLATE = 'The map with the most votes is: {} with {} votes!'

# The string to be formatted and sent to the server when a redo map vote option is chosen.
VOTE_REDO_MESSAGE_TEMPLATE = 'The redo option had the most votes ({} votes)'

# How long to listen to chat for vote casts in seconds.
DEFAULT_VOTING_TIME_DURATION_S = 30.0

# The default port for RCON.
DEFAULT_PORT = 21114

# The default URL to use to fetch the Squad map layers.
DEFAULT_LAYERS_URL = 'https://raw.githubusercontent.com/bsubei/squad_map_layers/master/layers.json'

# How long to sleep in between each "has the map changed" check (in seconds).
SLEEP_BETWEEN_MAP_CHECKS_S = 5.0

# How many of the next maps in the current rotation to choose as candidates for the map vote.
NUM_NEXT_MAPS_IN_ROTATION = 4

# The minimum number of players that request a map vote before a map vote is allowed.
NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD = 5

# The prefixed clan tag to use for clan players to force a map vote.
CLAN_TAG = '[FP]'

# The list of recognized map vote commands.
MAP_VOTE_COMMANDS = ['!mapvote', '!votemap', '!rtv']

# The text to display for the last option in the map vote (runs the map vote again with random candidates).
REDO_VOTE_OPTION = 'Run the vote again with random maps'


def has_map_vote_command(message):
    """ Helper that returns True if the message contains any of the map vote commands and False otherwise. """
    return any(1 for command in MAP_VOTE_COMMANDS if command in message)


def get_rotation_from_filepath(map_rotation_filepath):
    """
    Given the filepath to the map rotations file, return the list of map rotations. The file should list each map on a
    separate line.
    """
    # Fetches the map rotation from the given .txt file and returns it as a
    # list of strings (with newlines removed).
    with open(map_rotation_filepath, 'r') as f:
        return list(filter(None, [line.strip('\n') for line in f.readlines()]))


def get_map_candidates(map_rotation_filepath, map_layers_url, current_map):
    """
    Return the candidate map layers for a vote based on whether a rotation is provided or not.

    If a rotation is provided, then return a random skirmish map and the next NUM_NEXT_MAPS_IN_ROTATION maps in the
    rotation.

    If a rotation is not provided, then pick a random skirmish map and NUM_NEXT_MAPS_IN_ROTATION more random maps from
    the map layers JSON file.

    NOTE: it is assumed that the rotation has no duplicate layers (this is needed to figure out the next layers to
    choose in the rotation).

    :param map_rotation_filepath: str | None The filepath to the map rotation to use, or None.
    :param map_layers_url: str | None The URL to the map layers JSON file to use if the rotation is not provided.
    :param current_map: str The map layer that is currently being played.
    :return: list(str) The list of map layers to use as candidates in the map vote. The first is always a Skirmish map.
    """
    NO_FILEPATH = None
    # If a map rotation is provided, use the next N maps as candidates.
    if map_rotation_filepath:
        # Find the index of the current map in the rotation.
        map_rotation = get_rotation_from_filepath(map_rotation_filepath)
        try:
            next_map_index = map_rotation.index(current_map) + 1
            rotation_length = len(map_rotation)

            # Choose a random skirmish map plus the next N maps in the rotation as the candidates plus a redo option.
            random_skirmish = squad_map_randomizer.get_random_skirmish_layer(NO_FILEPATH, map_layers_url)
            candidates = [random_skirmish] + map_rotation[next_map_index:next_map_index + NUM_NEXT_MAPS_IN_ROTATION]

            # Wrap around the rotation list.
            if next_map_index + NUM_NEXT_MAPS_IN_ROTATION >= rotation_length:
                candidates += map_rotation[:next_map_index + NUM_NEXT_MAPS_IN_ROTATION - rotation_length]
            # Don't forget to include the redo option if none of the options are preferred.
            return candidates + [REDO_VOTE_OPTION]
        except ValueError:
            logger.error('Failed to find current map in rotation! Using random maps as candidates instead of rotation!')

    # Otherwise, just use random maps as candidates (and a redo option).
    all_map_layers = squad_map_randomizer.get_json_layers(NO_FILEPATH, map_layers_url)
    rotation = squad_map_randomizer.get_map_rotation(
                all_map_layers, num_starting_skirmish_maps=1, num_repeating_pattern=1)
    return squad_map_randomizer.get_layers(rotation) + [REDO_VOTE_OPTION]


def format_candidate_maps(candidate_maps):
    """ Returns a formatted string of all the candidate maps to be displayed to players in chat. """
    return '\n'.join([f'{index}) {candidate}' for index, candidate in enumerate(candidate_maps)])


def get_highest_map_vote(candidate_maps, player_messages):
    """
    Given a list of candidate maps and player messages (dict of player_id -> PlayerChat), return both the key
    and count for the highest map vote.

    NOTE: ties are broken by choosing the map first encountered (first voted on) in the given candidate maps list.

    :param candidate_maps: list(str) The list of candidate maps that are being voted on.
    :param player_messages: dict(str->PlayerChat) Contains the list of messages for each player (keyed by player_id).
    :return: tuple(str, int) The name of the winning map and the vote count it received. None if there are no votes.
    """
    # This is a counter that keeps track of the count for each map (key).
    map_votes = collections.Counter()

    # Go over every message and count it towards a map if you can use it as an
    # index. Otherwise, skip it.
    for player_id, player_chat in player_messages.items():
        if isinstance(player_chat.messages, str):
            raise ValueError(
                'Given list of messages is just a string, not a list!')

        # In order to avoid double-counting votes from a single voter, use their most recent valid vote and throw away
        # the rest of their votes.
        for message in reversed(player_chat.messages):
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
    Whenever a new map starts, call reset_map_vote() and you can then poll should_start_map_vote() and then call
    start_map_vote() when it's ready.
    """

    def __init__(self, squad_rcon_client,
                 voting_cooldown_s=DEFAULT_VOTING_COOLDOWN_S, voting_time_duration_s=DEFAULT_VOTING_TIME_DURATION_S):
        """
        The constructor for MapVoter.

        :param squad_rcon_client: RconConnection The handle to the rcon client.
        :param voting_time_duration_s: float The duration of time to wait for players to vote on maps in seconds.
        """
        # This stores the handle to the squad_rcon_client (so we can contact the squad server).
        self.squad_rcon_client = squad_rcon_client

        # How many seconds to wait for players to vote on a map.
        self.voting_time_duration_s = voting_time_duration_s

        # How many seconds to wait in between map votes.
        self.voting_cooldown_s = voting_cooldown_s

        # Flag to indicate that a map vote should be redone (with random maps) as soon as possible.
        self.redo_requested = False

        # The most recent player chat objects (dict of player id -> PlayerChat).
        self.recent_player_chat = {}

        # Reset map vote timer since we just started. This sets self.time_since_map vote to time now.
        self.reset_map_vote()

    def reset_map_vote(self):
        """
        This function should be called any time a map vote succeeded, in order to reset the map vote cooldown.
        """
        # This stores the time when the latest map vote succeeded (since the epoch).
        self.time_since_map_vote = time.time()

        # The set of players currently requesting a map vote.
        self.players_requesting_map_vote = set()

    def get_duration_since_map_vote(self):
        """ Returns the duration of time (in seconds) since the map started. """
        return time.time() - self.time_since_map_vote

    def get_duration_until_map_vote_available(self):
        """
        Return the duration (in seconds) until the map vote is available. A positive value means there is still time
        remaining until map vote can be called, and a zero or negative value means a map vote can start or has started
        already.
        """
        return self.voting_cooldown_s - self.get_duration_since_map_vote()

    def should_start_map_vote(self):
        """
        Returns True if the map vote should start, and False otherwise.

        If the map vote is available (enough time has elapsed since previous map vote), then a map vote
        should start if enough players have asked for it using MAP_VOTE_COMMANDS. A map vote should also start if any
        clan member uses a map vote command at any point (no time limit). The redo flag is used to instantly restart
        the map vote in case the previous map vote wanted a redo.
        """
        return ((self.get_duration_until_map_vote_available() <= 0 and self.did_enough_players_ask_for_map_vote()) or
                self.did_one_clan_member_ask_for_map_vote() or
                self.redo_requested)

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
        """
        Starts a map vote by sending candidate maps message and listening to chat for a specified duration. Blocks while
        the map vote is being done.
        """
        # Format the given list of map candidates.
        candidate_maps_formatted = format_candidate_maps(candidate_maps)
        logger.info(f'Starting a new map vote! Candidate maps:\n{candidate_maps_formatted}')

        # Send map vote message (includes list of candidates).
        start_vote_message = START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=candidate_maps_formatted)
        self.squad_rcon_client.exec_command(f'AdminBroadcast {start_vote_message}')

        # Clear the old player chat objects that might have accumulated before the vote started.
        self.squad_rcon_client.clear_player_chat()

        # Listen to the chat messages and collect them all as a dict of player_id -> PlayerChat where each player could
        # have posted a list of messages.
        self.listen_to_votes(self.voting_time_duration_s, start_vote_message)
        self.recent_player_chat = self.squad_rcon_client.get_player_chat()
        logger.debug(f'The received player messages were:\n{self.recent_player_chat}\n')

        # Parse the chat messages into votes, and choose the map with the highest votes.
        result = get_highest_map_vote(
            candidate_maps, self.recent_player_chat)
        if result:
            winner_map, vote_count = result
            # If the voting was valid and was not a redo option, send a message with the results, then set next map.
            if winner_map != REDO_VOTE_OPTION:
                vote_result_message = VOTE_RESULT_MESSAGE_TEMPLATE.format(
                    winner_map, vote_count)
                self.squad_rcon_client.exec_command(f'AdminBroadcast {vote_result_message}')
                logger.info(vote_result_message)
                self.squad_rcon_client.exec_command(f'AdminSetNextMap "{winner_map}"')
                # Reset map vote so calling another vote is on cooldown.
                self.reset_map_vote()
            # If the voting was valid but a redo option was chosen, run the map vote again (set redo_requested flag).
            else:
                vote_redo_message = VOTE_REDO_MESSAGE_TEMPLATE.format(vote_count)
                self.squad_rcon_client.exec_command(f'AdminBroadcast {vote_redo_message}')
                logger.info(vote_redo_message)
                self.redo_requested = True
        else:
            # Else, send a message saying voting failed. We do not reset because the map vote failed.
            vote_failed_message = 'The map vote failed!'
            self.squad_rcon_client.exec_command(f'AdminBroadcast {vote_failed_message}')
            logger.warning(vote_failed_message)

    def did_enough_players_ask_for_map_vote(self):
        """
        Returns True if enough players (above threshold) have recently requested a mapvote, and returns False otherwise.
        """
        previous_map_vote_requests = len(self.players_requesting_map_vote)
        # Check if any of the recent player messages had the map vote command in them.
        for player_id, player_chat in self.recent_player_chat.items():
            for message in player_chat.messages:
                if has_map_vote_command(message):
                    self.players_requesting_map_vote.add(player_id)
        # Tally up the counts of who wants a map vote.
        map_vote_requests = len(self.players_requesting_map_vote)
        num_asks_remaining = NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD - map_vote_requests
        enough_asked = num_asks_remaining <= 0
        # Send a broadcast message if new requests came in but more are needed.
        if not enough_asked and map_vote_requests != previous_map_vote_requests:
            self.squad_rcon_client.exec_command(
                f'AdminBroadcast {num_asks_remaining} more requests needed to start a map vote.')
        return enough_asked

    def did_one_clan_member_ask_for_map_vote(self):
        """
        Returns True if any clan members (see CLAN_TAG) recently requested a mapvote, and returns False otherwise.
        """
        for player_id, player_chat in self.recent_player_chat.items():
            for message in player_chat.messages:
                if has_map_vote_command(message) and CLAN_TAG in player_chat.player_name:
                    return True
        return False


def parse_cli():
    """ Parses sys.argv (commandline args) and returns a parser with the arguments. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--rcon-address', required=True, help='The address to the RCON server (IP or URL).')
    parser.add_argument('--rcon-port', type=int, help=f'The port for the RCON server. Defaults to {DEFAULT_PORT}.',
                        default=DEFAULT_PORT)
    parser.add_argument('--rcon-password', required=True, help='The password for the RCON server.')
    parser.add_argument('--voting-cooldown', type=float,
                        help=('How long to wait (in seconds) in between map votes. Defaults to '
                              f'{DEFAULT_VOTING_COOLDOWN_S}.'), default=DEFAULT_VOTING_COOLDOWN_S)
    parser.add_argument('--voting-duration', type=float,
                        help=f'How long to listen for votes in seconds. Defaults to {DEFAULT_VOTING_TIME_DURATION_S}.',
                        default=DEFAULT_VOTING_TIME_DURATION_S)
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                        help='Verbose flag to indicate that DEBUG level output should be logged.')
    parser.add_argument('--map-rotation-filepath',
                        help=('The filepath to the map rotation. If specified, the mapvoting choices will include the '
                              'next maps in the rotation. If unspecified, the choices will be a random set of maps '
                              'from the provided map layers JSON file.'))
    parser.add_argument('--map-layers-url', default=DEFAULT_LAYERS_URL,
                        help=('The URL to the map layers JSON file containing all map layers to use for the map vote '
                              'choices if a map rotation is not provided/used.'))
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

    # Set up the connection to RCON using a managed context (socket is closed automatically once we leave this context).
    with rcon.get_managed_rcon_connection(args.rcon_address, port=args.rcon_port, password=args.rcon_password) as conn:
        # Initialize the mapvoter.
        mapvoter = MapVoter(conn, args.voting_cooldown, args.voting_duration)

        logger.info(f'Will start checking for new map every {SLEEP_BETWEEN_MAP_CHECKS_S} seconds and waiting to start '
                    'a map vote...')

        # Get the current map at start so we know when the map changes.
        current_map, next_map = mapvoter.squad_rcon_client.get_current_and_next_map()

        # Spin until we're done, but do it slowly.
        while True:
            # Check if we started a new map, and reset the mapvoter timer if it did.
            current_map, next_map = mapvoter.squad_rcon_client.get_current_and_next_map()
            logger.debug(f'Current map: {current_map}, next map: {next_map}')

            # Print out how long until or since map vote.
            if mapvoter.get_duration_until_map_vote_available() > 0:
                logger.debug(f'Time until map vote is available: {mapvoter.get_duration_until_map_vote_available()}')
            else:
                logger.debug(f'Time since map vote was available: {-mapvoter.get_duration_until_map_vote_available()}')

            # Print out how many players have asked for a map vote so far.
            logger.debug(f'Number of players asking for map vote: {len(mapvoter.players_requesting_map_vote)}.')

            # If the next map is the same as current map, set a random map from the rotation as next map.
            # NOTE(bsubei): the vote could force two consecutive maps to be the same. This will prevent that from
            # happening.
            if current_map == next_map:
                random_map = random.choice(get_map_candidates(
                                            args.map_rotation_filepath, args.map_layers_url, current_map)[1:-1])
                logger.warning(f'Next map is same as current map! Setting to a random map: {random_map}')
                mapvoter.squad_rcon_client.exec_command(f'AdminSetNextMap "{random_map}"')

            # Get most recent player messages since we last asked for the current map.
            mapvoter.recent_player_chat = mapvoter.squad_rcon_client.get_player_chat()
            mapvoter.squad_rcon_client.clear_player_chat()

            # If it's time to vote, start the vote!
            if mapvoter.should_start_map_vote():
                # In the special case that a redo is requested, omit the rotation filepath so we pick random maps. Also
                # reset the redo flag.
                rotation_filepath = None if mapvoter.redo_requested else args.map_rotation_filepath
                mapvoter.redo_requested = False
                mapvoter.start_map_vote(get_map_candidates(rotation_filepath, args.map_layers_url, current_map))

            time.sleep(SLEEP_BETWEEN_MAP_CHECKS_S)


if __name__ == '__main__':
    main()
