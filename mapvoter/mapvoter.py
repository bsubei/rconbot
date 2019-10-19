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
# A class that handles map voting mechanics.
#
# TODO fill this out
#

import collections
import time
import logging

logger = logging.getLogger(__name__).addHandler(logging.NullHandler())


# Wait 1 minute before starting a map vote at the beginning of every map.
TIME_ELAPSED_BEFORE_STARTING_VOTE_S = 60

# The string to be formatted and sent to the server when a mapvote starts.
START_VOTE_MESSAGE_TEMPLATE = (
    'Please cast a vote for the next map by typing the corresponding number in AllChat.\n{candidate_maps}')
# The string to be formatted and sent to the server when a mapvote is over.
VOTE_RESULT_MESSAGE_TEMPLATE = 'The map with the most votes is: {} with {} votes!'

# How long to listen to chat for vote casts in seconds.
VOTING_TIME_DURATION_S = 30


def get_rotation_from_filepath(map_rotation_filepath):
    """ TODO """
    # Fetches the map rotation from the given .txt file and returns a list of strings.
    return []


def format_candidate_maps(candidate_maps):
    """ TODO """
    return '\n'.join(['{}) {}'.format(index, candidate) for index, candidate in enumerate(candidate_maps)])


class MapVoter:
    """ TODO docstring """

    def __init__(self, rconbot, map_rotation_filepath):
        # This stores the map rotation (the pool of available maps to sample candidates from).
        self.map_rotation_list = get_rotation_from_filepath(map_rotation_filepath)

        # This stores the handle to the rconbot (so we can contact the squad server).
        self.rconbot = rconbot

        # Since we just started, pretend we reset to a new map.
        self.reset_new_map()

    def get_candidate_maps(self):
        """ TODO """
        return []

    def reset_new_map(self):
        """ TODO """
        # This stores the time when the latest map started (since the epoch).
        self.time_map_started = time.time()

    def should_start_map_vote(self):
        """
        If the time since the most recent map has started is greater than a threshold, then return True. Otherwise,
        return False.
        """
        return (time.time() - self.time_map_started) >= TIME_ELAPSED_BEFORE_STARTING_VOTE_S

    def get_highest_map_vote(candidate_maps, player_messages):
        """ TODO """
        # This is a counter that keeps track of the count for each map (key).
        map_votes = collections.Counter()

        for player_id, messages in player_messages:
            # Go over every message and count it towards a map if you can use it as an index. Otherwise, skip it.
            for message in messages:
                try:
                    map_votes.update(candidate_maps[int(message)])
                except (ValueError, IndexError):
                    logger.warn('Player with id {} entered invalid mapvote message.'.format(player_id))
                    continue

        return map_votes.most_common(1)[0]

    def start_map_vote(self):
        """ TODO """
        # Get the list of map candidates (randomly chosen from the rotation).
        candidate_maps = self.get_candidate_maps()
        candidate_maps_formatted = format_candidate_maps(candidate_maps)

        # Send mapvote message (includes list of candidates).
        start_vote_message = START_VOTE_MESSAGE_TEMPLATE.format(candidate_maps=candidate_maps_formatted)
        self.rconbot.send_admin_message(start_vote_message)

        # Listen to the chat messages and collect them all as a dict of player_id -> list(str) where each player could
        # have posted a list of messages.
        player_messages = self.rconbot.listen_to_allchat_for_duration(VOTING_TIME_DURATION_S)

        # Parse the chat messages into votes, and choose the map with the highest votes.
        winner_map, vote_count = self.get_highest_map_vote(candidate_maps, player_messages)

        # Send a message with the results, then set next map.
        vote_result_message = VOTE_RESULT_MESSAGE_TEMPLATE.format(winner_map, vote_count)
        self.rconbot.send_admin_message(vote_result_message)
        self.rconbot.set_next_map(winner_map)
