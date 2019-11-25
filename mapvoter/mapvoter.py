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

import collections
import time
import logging
import re

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# Wait this much time before starting a map vote at the beginning of every map.
TIME_ELAPSED_BEFORE_STARTING_VOTE_S = 60 * 15

# The string to be formatted and sent to the server when a mapvote starts.
START_VOTE_MESSAGE_TEMPLATE = (
    'Please cast a vote for the next map by typing the corresponding number in AllChat.\n{candidate_maps}')
# The string to be formatted and sent to the server when a mapvote is over.
VOTE_RESULT_MESSAGE_TEMPLATE = 'The map with the most votes is: {} with {} votes!'

# How long to listen to chat for vote casts in seconds.
VOTING_TIME_DURATION_S = 30.0


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
    return '\n'.join(['{}) {}'.format(index, candidate)
                      for index, candidate in enumerate(candidate_maps)])


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
                logger.warning(
                    'Player with id {} entered invalid mapvote message {}. Skipping...'.format(player_id, message))

    return map_votes.most_common(1)[0] if map_votes else None


class MapVoter:
    """
    Instantiate this class and use it to send map voting instructions and listen to player responses (blocking).
    Whenever a new map starts, call reset_new_map() and you can then poll should_start_map_vote() and then call
    start_map_vote() when it's ready.
    """

    def __init__(
            self, squad_rcon_client,
            voting_time_duration_s=VOTING_TIME_DURATION_S):
        """
        The constructor for MapVoter.

        :param squad_rcon_client: SquadRCONClient The handle to the rcon client.
        :param voting_time_duration_s: float The duration of time to wait for players to vote on maps in seconds.
        """
        # This stores the handle to the squad_rcon_client (so we can contact the squad server).
        self.squad_rcon_client = squad_rcon_client

        # How many seconds to wait for players to vote on a map.
        self.voting_time_duration_s = voting_time_duration_s

        # Since we just started, pretend we reset to a new map. This sets self.time_map_started to time now.
        self.reset_new_map()

    def reset_new_map(self):
        """ This function should be called any time the map is reset, in order to reset time since map started. """
        # This stores the time when the latest map started (since the epoch).
        self.time_map_started = time.time()
        self.has_voted_on_this_map = False

    def should_start_map_vote(self):
        """
        If the time since the most recent map has started is greater than a threshold, and we haven't voted on this map
        before, then return True. Otherwise, return False.
        """
        return (
            (time.time() - self.time_map_started) >= TIME_ELAPSED_BEFORE_STARTING_VOTE_S and
            not self.has_voted_on_this_map)

    def start_map_vote(self, candidate_maps):
        """ Starts a map vote by sending candidate maps message and listening to chat for a specified duration. """
        # Mark the flag that we've voted on this map so we don't vote again.
        self.has_voted_on_this_map = True

        # Get the list of map candidates (randomly chosen from the rotation).
        candidate_maps_formatted = format_candidate_maps(candidate_maps)
        logger.info('Starting a new map vote! Candidate maps:\n{}'.format(
            candidate_maps_formatted))

        # Send mapvote message (includes list of candidates).
        start_vote_message = START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=candidate_maps_formatted)
        self.squad_rcon_client.send_admin_message(start_vote_message)

        # Listen to the chat messages and collect them all as a dict of player_id -> list(str) where each player could
        # have posted a list of messages.
        # NOTE: the list of player messages is given in chronological order. Only the last cast vote is counted.
        player_messages = self.squad_rcon_client.listen_to_allchat_for_duration(
            self.voting_time_duration_s, start_vote_message)
        logger.debug('the received player messages were:\n{}'.format(player_messages))

        # Parse the chat messages into votes, and choose the map with the highest votes.
        result = get_highest_map_vote(
            candidate_maps, player_messages)
        if result:
            # If the voting was valid, send a message with the results, then set next map.
            winner_map, vote_count = result
            vote_result_message = VOTE_RESULT_MESSAGE_TEMPLATE.format(
                winner_map, vote_count)
            self.squad_rcon_client.send_admin_message(vote_result_message)
            logger.info(vote_result_message)
            self.squad_rcon_client.set_next_map(winner_map)
        else:
            # Else, send a message saying voting failed and reset so it starts the vote again later.
            vote_failed_message = 'The map vote failed!'
            self.squad_rcon_client.send_admin_message(vote_failed_message)
            logger.warning(vote_failed_message)
            self.reset_new_map()
