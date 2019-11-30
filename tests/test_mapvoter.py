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
# A testing class to test the MapVoter functionality.
#

import pytest
from unittest import mock

from mapvoter import mapvoter

# Some constants used in mock objects.
FAKE_ROTATION_FILEPATH = 'some ignored fake filepath'
FAKE_ROTATION = ['not a real', 'rotation', 'list']
NUMBER_OF_CANDIDATES = 2
FAKE_CANDIDATE_MAPS = ['vote me', 'no me pls', 'best map EU']
FAKE_VOTE_DURATION_S = 42.0
TIME_NOW = 69.0

# TODO needs updating

class TestMapVoter:
    """ Test class (uses pytest) for the MapVoter class. """

    MOCK_RCON_CLIENT = mock.MagicMock()

    @pytest.fixture
    def voter(self):
        """ The fixture function to return a mapvoter. """
        TestMapVoter.MOCK_RCON_CLIENT.send_admin_message = mock.MagicMock()
        TestMapVoter.MOCK_RCON_CLIENT.listen_to_allchat_for_duration = mock.MagicMock()
        TestMapVoter.MOCK_RCON_CLIENT.set_next_map = mock.MagicMock()
        with mock.patch('mapvoter.mapvoter.get_rotation_from_filepath') as fake_get_rotation:
            with mock.patch('mapvoter.mapvoter.time.time') as fake_time:
                fake_get_rotation.return_value = FAKE_ROTATION
                fake_time.return_value = TIME_NOW
                return mapvoter.MapVoter(
                    TestMapVoter.MOCK_RCON_CLIENT, FAKE_ROTATION_FILEPATH, NUMBER_OF_CANDIDATES, FAKE_VOTE_DURATION_S)

    def test_get_rotation_from_filepath(self, tmp_path):
        """ Tests the get_rotation_from_filepath function. """
        # Write out the fake rotation to the filepath.
        filepath = tmp_path / 'somefile.txt'
        filepath.write_text('\n'.join(FAKE_ROTATION))

        # Read it back in with get_rotation_from_filepath. We expect them to be the same.
        assert mapvoter.get_rotation_from_filepath(filepath) == FAKE_ROTATION

    def test_format_candidate_maps(self):
        """ Tests the format_candidate_maps function. """
        # Case 1: test multiple maps.
        EXPECTED_CANDIDATE_MAPS_STRING = (
            '0) vote me\n'
            '1) no me pls\n'
            '2) best map EU')
        assert mapvoter.format_candidate_maps(
            FAKE_CANDIDATE_MAPS) == EXPECTED_CANDIDATE_MAPS_STRING

        # Case 2: test a single map.
        assert mapvoter.format_candidate_maps(['a map']) == '0) a map'

        # Case 3: test on an empty list of maps.
        assert mapvoter.format_candidate_maps([]) == ''

    def test_get_highest_map_vote(self):
        """ Tests for get_highest_map_vote. """

        # Case 1: there are no player messages. Return None.
        assert mapvoter.get_highest_map_vote(FAKE_CANDIDATE_MAPS, {}) is None

        # Case 2a: there are no valid player messages that can be parsed as votes. Return None.
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {'id1': ['not an int'], 'id2': ['also not an int']}) is None
        # Case 2b: a variant of the previous but with ints that are invalid.
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {'id1': ['10000'], 'id2': ['-22']}) is None

        # Case 3: there is only one valid vote cast (double votes by one player are ignored). Return the winning map.
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS,
            {'id1': ['not an int'], 'id2': ['1', 'changed my mind', '0']}) == (FAKE_CANDIDATE_MAPS[0], 1)

        # Case 4: there are many valid votes but only for one map. Return the winning map.
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {
                'id1': ['0', 'not an int'],
                'id2': ['yay', '0'],
                'id3': [],
                'id4': ['0']
            }) == (FAKE_CANDIDATE_MAPS[0], 3)

        # Case 5: there are many valid votes for multiple maps. Return the winning map.
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {
                'id1': ['0', 'not an int'],
                'id2': ['yay', '1'],
                'id3': ['2'],
                'id4': ['1']
            }) == (FAKE_CANDIDATE_MAPS[1], 2)

        # Case 6: ties are broken by choosing the element first encountered (first voted on) in the candidate maps.
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {
                'id1': ['2', 'not an int'],
                'id2': ['yay', '1'],
                'id3': ['2'],
                'id4': ['1']
            }) == (FAKE_CANDIDATE_MAPS[2], 2)

    def test_constructor(self, voter):
        """ Tests the constructor for the MapVoter class. """
        # Check that each member was assigned as we expected from the fixture (includes mocked time).
        assert voter.map_rotation_list == FAKE_ROTATION
        assert voter.rcon_client == TestMapVoter.MOCK_RCON_CLIENT
        assert voter.number_of_candidates == NUMBER_OF_CANDIDATES
        assert voter.voting_time_duration_s == FAKE_VOTE_DURATION_S
        assert voter.time_map_started == TIME_NOW
        assert not voter.has_voted_on_this_map

    def test_get_candidate_maps(self, voter):
        """ Tests the get_candidate_maps function. """
        # Case 1: test on the default voter fixture. Every candidate map exists in the original list we sampled from.
        candidate_maps = voter.get_candidate_maps()
        for m in candidate_maps:
            assert m in voter.map_rotation_list
        assert len(candidate_maps) == voter.number_of_candidates

        # Case 2: modify the number of candidates:
        # Case 2a: number of candidates equal to number of maps to sample from.
        voter.number_of_candidates = len(voter.map_rotation_list)
        assert sorted(voter.get_candidate_maps()) == sorted(
            voter.map_rotation_list)

        # Case 2b: number of candidates greater than number of maps to sample from (raises an error).
        voter.number_of_candidates = len(voter.map_rotation_list) + 1
        with pytest.raises(ValueError):
            voter.get_candidate_maps()

        # Case 2c: number of candidates equal to zero.
        voter.number_of_candidates = 0
        assert voter.get_candidate_maps() == []

    def test_reset_new_map(self, voter):
        """ Tests for reset_new_map. """
        # Case 1: When a map is reset, the time_map_started should always be later than the original (before restart).
        # This assumes time.time() works as intended.
        initial_time = voter.time_map_started
        voter.reset_new_map()
        later_time = voter.time_map_started
        assert later_time > initial_time

        # Case 2: calling reset_new_map uses time.time() exactly as we expect.
        with mock.patch('mapvoter.mapvoter.time.time') as mock_time:
            mock_time.return_value = TIME_NOW
            voter.reset_new_map()
        assert voter.time_map_started == TIME_NOW

        # Case 3: resetting a map should reset has_voted_on_this_map flag.
        assert not voter.has_voted_on_this_map
        voter.reset_new_map()
        assert not voter.has_voted_on_this_map
        voter.has_voted_on_this_map = True
        voter.reset_new_map()
        assert not voter.has_voted_on_this_map

    def check_should_start_map_vote(voter, time_map_started, time_now, expected_should_start):
        """
        Helper to check whether a voter should start map vote based on the time the map started and the current time.
        """
        voter.time_map_started = time_map_started
        with mock.patch('mapvoter.mapvoter.time.time') as mock_time:
            mock_time.return_value = time_now
            assert expected_should_start == voter.should_start_map_vote()

    def test_should_start_map_vote(self, voter):
        """ Tests for should_start_map_vote. """
        # Case 1: only changing time, not the has_voted_on_this_map flag.
        # Case 1a: On startup, a mapvoter should never want to start a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW, False)

        # Case 1b: After not enough time has elapsed, a mapvoter should not want to start a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + mapvoter.TIME_ELAPSED_BEFORE_STARTING_VOTE_S - 1.0, False)

        # Case 1c: After enough time has elapsed, a mapvoter should want to start a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + mapvoter.TIME_ELAPSED_BEFORE_STARTING_VOTE_S + 1.0, True)

        # Case 1d: if time has gone back (negative elapsed time), still return should not start map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW - 100000.0, False)

        # Case 2: Change has_voted_on_this_map flag.
        voter.has_voted_on_this_map = True
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + mapvoter.TIME_ELAPSED_BEFORE_STARTING_VOTE_S + 1.0, False)
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + mapvoter.TIME_ELAPSED_BEFORE_STARTING_VOTE_S - 1.0, False)

    def test_start_map_vote_fails(self, voter):
        """ Tests for start_map_vote when it fails. """
        # Start a map vote that fails (no reply from users).
        voter.rcon_client.listen_to_allchat_for_duration.return_value = {}
        assert not voter.has_voted_on_this_map
        voter.start_map_vote()

        # Check that calling start_map_vote changes the has_voted_on_this_map flag.
        assert voter.has_voted_on_this_map
        # Check that the start vote message is sent using the rcon_client.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.partition('{')[0] in
                voter.rcon_client.send_admin_message.call_args_list[0][0][0])
        # Check that the map vote failed message is sent using the rcon_client.
        assert (voter.rcon_client.send_admin_message.call_args_list[1][0][0] ==
                'The map vote failed! Tell an admin to change the map if you want!')
        # Check that set_next_map is NOT called.
        assert voter.rcon_client.set_next_map.call_count == 0

    def test_start_map_vote_succeeds(self, voter):
        """ Tests for start_map_vote when it succeeds. """
        # Start a map vote that succeeds we have to mock get_candidate_maps so we know what we voted for.
        PREDETERMINED_WINNER_MAP = 'foobar'
        PREDETERMINED_WINNER_COUNT = 200
        with mock.patch('mapvoter.mapvoter.get_highest_map_vote') as fake_get_highest_map_vote:
            fake_get_highest_map_vote.return_value = (
                PREDETERMINED_WINNER_MAP, PREDETERMINED_WINNER_COUNT)
            voter.rcon_client.listen_to_allchat_for_duration.return_value = {
                'only player': ['I shall vote', '0']}
            assert not voter.has_voted_on_this_map
            voter.start_map_vote()

        # Check that calling start_map_vote changes the has_voted_on_this_map flag.
        assert voter.has_voted_on_this_map
        # Check that the start vote message is sent using the rcon_client.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.partition('{')[0] in
                voter.rcon_client.send_admin_message.call_args_list[0][0][0])
        # Check that the winning map message is sent using the rcon_client.
        assert voter.rcon_client.send_admin_message.call_args_list[1][0][0] == mapvoter.VOTE_RESULT_MESSAGE_TEMPLATE.format(
            PREDETERMINED_WINNER_MAP, PREDETERMINED_WINNER_COUNT)
        # Check that set_next_map is called.
        assert voter.rcon_client.set_next_map.call_count == 1
        assert voter.rcon_client.set_next_map.call_args[0][0] == PREDETERMINED_WINNER_MAP
