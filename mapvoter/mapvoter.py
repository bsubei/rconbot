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

import time


# Wait 1 minute before starting a map vote at the beginning of every map.
TIME_ELAPSED_BEFORE_STARTING_VOTE_S = 60


class MapVoter:
    """ TODO docstring """

    def __init__(self):
        self.reset_new_map()

    def reset_new_map(self):
        # This stores the time when the latest map started (since the epoch).
        self.time_map_started = time.time()

    def should_start_map_vote(self):
        """
        If the time since the most recent map has started is greater than a threshold, then return True. Otherwise,
        return False.
        """
        return (time.time() - self.time_map_started) >= TIME_ELAPSED_BEFORE_STARTING_VOTE_S
