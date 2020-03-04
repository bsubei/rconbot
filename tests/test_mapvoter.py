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
import random
from unittest import mock

from mapvoter import mapvoter

# Some constants used in mock objects.
FAKE_ROTATION_FILEPATH = 'some ignored fake filepath'
FAKE_ROTATION = ['not a real', 'rotation', 'list']
NUMBER_OF_CANDIDATES = 2
FAKE_CANDIDATE_MAPS = ['vote me', 'no me pls', 'best map EU']
FAKE_VOTE_DURATION_S = 42.0
FAKE_VOTE_COOLDOWN_S = 77.0
TIME_NOW = 69.0


class TestMapVoter:
    """ Test class (uses pytest) for the MapVoter class. """

    MOCK_RCON_CLIENT = mock.MagicMock()

    @pytest.fixture
    def voter(self):
        """ The fixture function to return a mapvoter. """
        TestMapVoter.MOCK_RCON_CLIENT.exec_command = mock.MagicMock()
        TestMapVoter.MOCK_RCON_CLIENT.clear_player_chat = mock.MagicMock()
        TestMapVoter.MOCK_RCON_CLIENT.get_player_chat = mock.MagicMock()
        with mock.patch('mapvoter.mapvoter.time.time') as fake_time:
            fake_time.return_value = TIME_NOW
            return mapvoter.MapVoter(
                TestMapVoter.MOCK_RCON_CLIENT, FAKE_VOTE_COOLDOWN_S, FAKE_VOTE_DURATION_S)

    def test_get_rotation_from_filepath(self, tmp_path):
        """ Tests the get_rotation_from_filepath function. """
        # Write out the fake rotation to the filepath.
        filepath = tmp_path / 'somefile.txt'
        filepath.write_text('\n'.join(FAKE_ROTATION))

        # Read it back in with get_rotation_from_filepath. We expect them to be the same.
        assert mapvoter.get_rotation_from_filepath(filepath) == FAKE_ROTATION

    def test_get_map_candidates(self):
        """ Tests the get_map_candidates function. """
        VALID_ROTATION_FILEPATH = 'a valid filepath'
        VALID_CURRENT_MAP = 'a valid current map'
        VALID_URL = 'a valid url'
        NO_URL = None
        SKIRMISH_LAYER = 'a skirmish layer'

        with mock.patch('mapvoter.mapvoter.get_rotation_from_filepath') as mock_get_rotation:
            with mock.patch('squad_map_randomizer.get_random_skirmish_layer') as mock_get_skirmish:
                # The rotation will have this skirmish layer appended to it.
                mock_get_skirmish.return_value = SKIRMISH_LAYER

                # Case 1a: provide all three arguments (map rotation filepath, layers URL, and current map). With
                # current map being in the middle of the rotation.
                mock_get_rotation.return_value = [str(x) for x in range(
                    5)] + [VALID_CURRENT_MAP] + [str(x) for x in range(5, 10)]
                assert mapvoter.get_map_candidates(VALID_ROTATION_FILEPATH, VALID_URL, VALID_CURRENT_MAP) == [
                    SKIRMISH_LAYER, '5', '6', '7', '8', mapvoter.REDO_VOTE_OPTION]

                # Case 1b: provide all three arguments (map rotation filepath, layers URL, and current map). With
                # current map being near the end of the rotation (to test for correct wrapping around the list).
                mock_get_rotation.return_value = [str(x) for x in range(
                    8)] + [VALID_CURRENT_MAP] + [str(x) for x in range(8, 10)]
                assert mapvoter.get_map_candidates(VALID_ROTATION_FILEPATH, VALID_URL, VALID_CURRENT_MAP) == [
                    SKIRMISH_LAYER, '8', '9', '0', '1', mapvoter.REDO_VOTE_OPTION]

                # Case 1c: provide all three arguments (map rotation filepath, layers URL, and current map). With
                # current map being in the end of the rotation.
                mock_get_rotation.return_value = [
                    str(x) for x in range(10)] + [VALID_CURRENT_MAP]
                assert mapvoter.get_map_candidates(VALID_ROTATION_FILEPATH, VALID_URL, VALID_CURRENT_MAP) == [
                    SKIRMISH_LAYER, '0', '1', '2', '3', mapvoter.REDO_VOTE_OPTION]

                # Case 1d: provide all three arguments (map rotation filepath, layers URL, and current map). With
                # current map being in the beginning of the rotation.
                mock_get_rotation.return_value = [
                    VALID_CURRENT_MAP] + [str(x) for x in range(10)]
                assert mapvoter.get_map_candidates(VALID_ROTATION_FILEPATH, VALID_URL, VALID_CURRENT_MAP) == [
                    SKIRMISH_LAYER, '0', '1', '2', '3', mapvoter.REDO_VOTE_OPTION]

        # Case 2: Provide an invalid layers URL (expect a failure).
        with mock.patch('mapvoter.mapvoter.get_rotation_from_filepath') as mock_get_rotation:
            mock_get_rotation.return_value = [VALID_CURRENT_MAP]
            with pytest.raises(ValueError):
                mapvoter.get_map_candidates(
                    VALID_ROTATION_FILEPATH, NO_URL, VALID_CURRENT_MAP)

        # Case 3: Provide rotation filepath but current_map cannot be found in that rotation.
        with mock.patch('mapvoter.mapvoter.get_rotation_from_filepath') as mock_get_rotation:
            mock_get_rotation.return_value = [str(x) for x in range(10)]
            with mock.patch('squad_map_randomizer.get_random_skirmish_layer') as mock_get_skirmish:
                # The rotation will have this skirmish layer appended to it.
                mock_get_skirmish.return_value = SKIRMISH_LAYER
                with pytest.raises(ValueError):
                    mapvoter.get_map_candidates(
                        VALID_ROTATION_FILEPATH, VALID_URL, VALID_CURRENT_MAP)

        # Case 4: No rotation filepath is provided, so it uses random layers from the JSON layers URL.
        NO_ROTATION_FILEPATH = None
        EXPECTED_CANDIDATES = ['the expected rotation']
        with mock.patch('squad_map_randomizer.get_json_layers'), mock.patch('squad_map_randomizer.get_map_rotation'):
            with mock.patch('squad_map_randomizer.get_layers') as mock_get_layers:
                mock_get_layers.return_value = EXPECTED_CANDIDATES
                assert mapvoter.get_map_candidates(
                    NO_ROTATION_FILEPATH, VALID_URL, VALID_CURRENT_MAP) == EXPECTED_CANDIDATES + [
                        mapvoter.REDO_VOTE_OPTION]

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
        # Some setup class for mocking PlayerChat objects.

        def chat_init(self, messages):
            self.messages = messages
        player_chat_class = type('temp_player_chat', (object,), {
                                 '__init__': chat_init})

        # Case 1: there are no player messages. Return None.
        assert mapvoter.get_highest_map_vote(FAKE_CANDIDATE_MAPS, {}) is None

        # Case 2a: there are no valid player messages that can be parsed as votes. Return None.
        player_chat1 = player_chat_class([' bla bla', 'not valid messages'])
        player_chat2 = player_chat_class(['not valid', 'ignore me'])
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {'id1': player_chat1, 'id2': player_chat2}) is None
        # Case 2b: a variant of the previous but with ints that are invalid.
        player_chat1 = player_chat_class(['10000'])
        player_chat2 = player_chat_class(['-22'])
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {'id1': player_chat1, 'id2': player_chat2}) is None

        # Case 3: there is only one valid vote cast (double votes by one player are ignored). Return the winning map.
        player_chat1 = player_chat_class(['not an int'])
        player_chat2 = player_chat_class(['1', 'changed my mind', '0'])
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS,
            {'id1': player_chat1, 'id2': player_chat2}) == (FAKE_CANDIDATE_MAPS[0], 1)

        # Case 4: there are many valid votes but only for one map. Return the winning map.
        player_chat1 = player_chat_class(['0', 'not an int'])
        player_chat2 = player_chat_class(['yay', '0'])
        player_chat3 = player_chat_class([])
        player_chat4 = player_chat_class(['0'])
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {
                'id1': player_chat1,
                'id2': player_chat2,
                'id3': player_chat3,
                'id4': player_chat4,
            }) == (FAKE_CANDIDATE_MAPS[0], 3)

        # Case 5: there are many valid votes for multiple maps. Return the winning map.
        player_chat1 = player_chat_class(['0', 'not an int'])
        player_chat2 = player_chat_class(['yay', '1'])
        player_chat3 = player_chat_class(['2'])
        player_chat4 = player_chat_class(['1'])
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {
                'id1': player_chat1,
                'id2': player_chat2,
                'id3': player_chat3,
                'id4': player_chat4,
            }) == (FAKE_CANDIDATE_MAPS[1], 2)

        # Case 6: ties are broken by choosing the element first encountered (first voted on) in the candidate maps.
        player_chat1 = player_chat_class(['2', 'not an int'])
        player_chat2 = player_chat_class(['yay', '1'])
        player_chat3 = player_chat_class(['2'])
        player_chat4 = player_chat_class(['1'])
        assert mapvoter.get_highest_map_vote(
            FAKE_CANDIDATE_MAPS, {
                'id1': player_chat1,
                'id2': player_chat2,
                'id3': player_chat3,
                'id4': player_chat4,
            }) == (FAKE_CANDIDATE_MAPS[2], 2)

    def test_constructor(self, voter):
        """ Tests the constructor for the MapVoter class. """
        # Check that each member was assigned as we expected from the fixture (includes mocked time).
        assert voter.squad_rcon_client == TestMapVoter.MOCK_RCON_CLIENT
        assert voter.voting_time_duration_s == FAKE_VOTE_DURATION_S
        assert voter.voting_cooldown_s == FAKE_VOTE_COOLDOWN_S
        assert len(voter.recent_player_chat) == 0
        assert voter.time_since_map_vote == TIME_NOW
        assert len(voter.players_requesting_map_vote) == 0

    def test_reset_map_vote(self, voter):
        """ Tests for reset_map_vote. """
        # Case 1: When a map vote is reset, the time_since_map_vote should always be later than the original (before
        # restart). This assumes time.time() works as intended.
        initial_time = voter.time_since_map_vote
        voter.reset_map_vote()
        later_time = voter.time_since_map_vote
        assert later_time > initial_time

        # Case 2: calling reset_map_vote uses time.time() exactly as we expect.
        with mock.patch('mapvoter.mapvoter.time.time') as mock_time:
            mock_time.return_value = TIME_NOW
            voter.reset_map_vote()
        assert voter.time_since_map_vote == TIME_NOW

        # Case 3: resetting a map vote should reset the players_requesting_map_vote set.
        assert voter.players_requesting_map_vote == set()
        voter.reset_map_vote()
        assert voter.players_requesting_map_vote == set()
        voter.players_requesting_map_vote = set(range(10))
        voter.reset_map_vote()
        assert voter.players_requesting_map_vote == set()

    def test_get_duration_until_map_vote_available(self, voter):
        """ Tests for get_duration_until_map_vote_available. """
        TIME_NOW = 800.0
        with mock.patch('mapvoter.mapvoter.time.time') as fake_time:
            fake_time.return_value = TIME_NOW
            assert voter.get_duration_until_map_vote_available() == (FAKE_VOTE_COOLDOWN_S -
                                                                     TIME_NOW + voter.time_since_map_vote)

    def check_should_start_map_vote(
            voter, time_since_map_vote, time_now, is_vote_requested, is_clan_member_requested, expected_should_start):
        """
        Helper to check whether a voter should start map vote based on the time of the latest vote and the current time.
        """
        voter.time_since_map_vote = time_since_map_vote
        with mock.patch('mapvoter.mapvoter.time.time') as mock_time:
            mock_time.return_value = time_now
            with mock.patch.object(voter, 'did_enough_players_ask_for_map_vote') as mock_vote_requested, (
                    mock.patch.object(voter, 'did_one_clan_member_ask_for_map_vote')) as mock_clan_requested:
                mock_vote_requested.return_value = is_vote_requested
                mock_clan_requested.return_value = is_clan_member_requested
                assert expected_should_start == voter.should_start_map_vote()

    def test_should_start_map_vote(self, voter):
        """ Tests for should_start_map_vote. """
        VOTE_REQUESTED = True
        VOTE_NOT_REQUESTED = False
        CLAN_MEMBER_REQUESTED = True
        CLAN_MEMBER_NOT_REQUESTED = False

        # Case 1: when map votes are requested, we can test the timer cooldown.
        # Case 1a: On startup, a mapvoter should be unable to start a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW, VOTE_REQUESTED, CLAN_MEMBER_NOT_REQUESTED, False)

        # Case 1b: After not enough time has elapsed, a mapvoter should still be unable to start a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s -
            1.0, VOTE_REQUESTED, CLAN_MEMBER_NOT_REQUESTED,
            False)

        # Case 1c: After enough time has elapsed, a mapvoter should be able to start a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s +
            1.0, VOTE_REQUESTED, CLAN_MEMBER_NOT_REQUESTED,
            True)

        # Case 1d: if time has gone back (negative elapsed time), still return should not start map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW - 100000.0, VOTE_REQUESTED, CLAN_MEMBER_NOT_REQUESTED, False)

        # Case 2: When map vote is never requested, never start a map vote no matter how much time passes.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s +
            1.0, VOTE_NOT_REQUESTED, CLAN_MEMBER_NOT_REQUESTED,
            False)
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s -
            1.0, VOTE_NOT_REQUESTED, CLAN_MEMBER_NOT_REQUESTED,
            False)

        # Case 3: If map vote requested after enough time has elapsed, allow a map vote.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s -
            1.0, VOTE_NOT_REQUESTED, CLAN_MEMBER_NOT_REQUESTED,
            False)
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s +
            1.0, VOTE_REQUESTED, CLAN_MEMBER_NOT_REQUESTED,
            True)

        # Case 4: If a clan member requested a vote, then allow a map vote regardless of anything else.
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s -
            1.0, VOTE_NOT_REQUESTED, CLAN_MEMBER_REQUESTED,
            True)
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s -
            1.0, VOTE_REQUESTED, CLAN_MEMBER_REQUESTED,
            True)
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s +
            1.0, VOTE_NOT_REQUESTED, CLAN_MEMBER_REQUESTED,
            True)
        TestMapVoter.check_should_start_map_vote(
            voter, TIME_NOW, TIME_NOW + voter.voting_cooldown_s +
            1.0, VOTE_REQUESTED, CLAN_MEMBER_REQUESTED,
            True)

    def test_start_map_vote_fails(self, voter):
        """ Tests for start_map_vote when it fails. """
        # Start a map vote that fails (no reply from users).
        with mock.patch('mapvoter.mapvoter.time.sleep'):
            voter.start_map_vote(FAKE_CANDIDATE_MAPS)

        # Check that the start vote message is sent using the squad_rcon_client.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=mapvoter.format_candidate_maps(FAKE_CANDIDATE_MAPS)) in
            voter.squad_rcon_client.exec_command.call_args_list[0][0][0])

        # Check that the halftime and finish messages are sent.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=mapvoter.format_candidate_maps(FAKE_CANDIDATE_MAPS)) in
            voter.squad_rcon_client.exec_command.call_args_list[1][0][0])
        assert (voter.squad_rcon_client.exec_command.call_args_list[2][0][0] ==
                'AdminBroadcast Voting is over!')

        # Check that the map vote failed message is sent using the squad_rcon_client.
        assert (voter.squad_rcon_client.exec_command.call_args_list[3][0][0] ==
                'AdminBroadcast The map vote failed!')

        # Check that the next map was NOT set.
        for args in voter.squad_rcon_client.exec_command.call_args_list:
            assert 'AdminSetNextMap' not in args[0][0]
        assert voter.squad_rcon_client.exec_command.call_count == 4

    def test_start_map_vote_succeeds(self, voter):
        """ Tests for start_map_vote when it succeeds. """
        # Start a map vote that succeeds. We have to mock get_candidate_maps so we know what we voted for.
        PREDETERMINED_WINNER_MAP = 'foobar'
        PREDETERMINED_WINNER_COUNT = 200
        with mock.patch('mapvoter.mapvoter.get_highest_map_vote') as fake_get_highest_map_vote, (
                mock.patch('mapvoter.mapvoter.time.sleep')):
            fake_get_highest_map_vote.return_value = (
                PREDETERMINED_WINNER_MAP, PREDETERMINED_WINNER_COUNT)
            voter.start_map_vote(FAKE_CANDIDATE_MAPS)

        # Check that the start vote message is sent using the squad_rcon_client.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=mapvoter.format_candidate_maps(FAKE_CANDIDATE_MAPS)) in
            voter.squad_rcon_client.exec_command.call_args_list[0][0][0])

        # Check that the halftime and finish messages are sent.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=mapvoter.format_candidate_maps(FAKE_CANDIDATE_MAPS)) in
            voter.squad_rcon_client.exec_command.call_args_list[1][0][0])
        assert (voter.squad_rcon_client.exec_command.call_args_list[2][0][0] ==
                'AdminBroadcast Voting is over!')

        # Check that the winning map message is sent using the squad_rcon_client.
        assert mapvoter.VOTE_RESULT_MESSAGE_TEMPLATE.format(
            PREDETERMINED_WINNER_MAP,
            PREDETERMINED_WINNER_COUNT) in voter.squad_rcon_client.exec_command.call_args_list[3][0][0]

        # Check that the next map was set.
        assert (f'AdminSetNextMap "{PREDETERMINED_WINNER_MAP}"'
                == voter.squad_rcon_client.exec_command.call_args_list[4][0][0])

        # Check that the redo_requested flag was NOT set.
        assert not voter.redo_requested

    def test_start_map_vote_redo(self, voter):
        """ Tests for start_map_vote when the vote is for the redo option. """
        # Start a map vote that succeeds. We have to mock get_candidate_maps so we know what we voted for.
        PREDETERMINED_WINNER_MAP = mapvoter.REDO_VOTE_OPTION
        PREDETERMINED_WINNER_COUNT = 200
        with mock.patch('mapvoter.mapvoter.get_highest_map_vote') as fake_get_highest_map_vote, (
                mock.patch('mapvoter.mapvoter.time.sleep')):
            fake_get_highest_map_vote.return_value = (
                PREDETERMINED_WINNER_MAP, PREDETERMINED_WINNER_COUNT)
            voter.start_map_vote(FAKE_CANDIDATE_MAPS)

        # Check that the start vote message is sent using the squad_rcon_client.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=mapvoter.format_candidate_maps(FAKE_CANDIDATE_MAPS)) in
            voter.squad_rcon_client.exec_command.call_args_list[0][0][0])

        # Check that the halftime and finish messages are sent.
        assert (mapvoter.START_VOTE_MESSAGE_TEMPLATE.format(
            candidate_maps=mapvoter.format_candidate_maps(FAKE_CANDIDATE_MAPS)) in
            voter.squad_rcon_client.exec_command.call_args_list[1][0][0])
        assert (voter.squad_rcon_client.exec_command.call_args_list[2][0][0] ==
                'AdminBroadcast Voting is over!')

        # Check that the redo vote message is sent using the squad_rcon_client.
        assert mapvoter.VOTE_REDO_MESSAGE_TEMPLATE.format(
            PREDETERMINED_WINNER_COUNT) in voter.squad_rcon_client.exec_command.call_args_list[3][0][0]

        # Check that the next map was NOT set.
        assert voter.squad_rcon_client.exec_command.call_count == 4
        for args in voter.squad_rcon_client.exec_command.call_args_list:
            assert 'AdminSetNextMap' not in args[0][0]

        # Check that the redo_requested flag was set.
        assert voter.redo_requested

    def test_did_enough_players_ask_for_map_vote(self, voter):
        """ Tests for did_enough_players_ask_for_map_vote. """
        # Some setup class for mocking PlayerChat objects.

        def chat_init(self, messages):
            self.messages = messages
        player_chat_class = type('temp_player_chat', (object,), {
                                 '__init__': chat_init})

        # Case 1: if no one asked, then expect False.
        assert not voter.did_enough_players_ask_for_map_vote()
        # We also check that no broadcast message was sent since no one asked for a map vote.
        assert voter.squad_rcon_client.exec_command.call_count == 0

        # Case 2: if only one person asks, expect False.
        voter.recent_player_chat = {'id1': player_chat_class(['!mapvote'])}
        assert not voter.did_enough_players_ask_for_map_vote()
        # Since one person asked, we check that a broadcast message was sent.
        assert voter.squad_rcon_client.exec_command.call_count == 1
        assert (f'AdminBroadcast {mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD - 1} more requests' in
                voter.squad_rcon_client.exec_command.call_args_list[0][0][0])

        # NOTE(bsubei): we must reset to remove the previous map vote requests and chat.
        voter.reset_map_vote()
        voter.recent_player_chat = {}

        # Case 3: if not enough players ask (just below the threshold), expect False.
        voter.recent_player_chat = {
            f'id{i}': player_chat_class(['!mapvote']) for i in range(
                0, mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD - 1)}
        assert not voter.did_enough_players_ask_for_map_vote()

        # NOTE(bsubei): we must reset to remove the previous map vote requests and chat.
        voter.reset_map_vote()
        voter.recent_player_chat = {}

        # Case 4: if exactly enough players ask, expect True
        voter.recent_player_chat = {
            f'id{i}': player_chat_class(['!mapvote']) for i in range(
                0, mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD)}
        assert voter.did_enough_players_ask_for_map_vote()

        # NOTE(bsubei): we must reset to remove the previous map vote requests and chat.
        voter.reset_map_vote()
        voter.recent_player_chat = {}

        # Case 5: if more than enough players ask, expect True
        voter.recent_player_chat = {
            f'id{i}': player_chat_class(['!mapvote']) for i in range(
                0, mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD + 1)}
        assert voter.did_enough_players_ask_for_map_vote()

        # NOTE(bsubei): we must reset to remove the previous map vote requests and chat.
        voter.reset_map_vote()
        voter.recent_player_chat = {}

        # Case 6: if some players have duplicate map votes, don't count them.
        voter.recent_player_chat = {
            f'id{i}': player_chat_class(['!mapvote', f'{i} some chat', 'another !mapvote'])
            for i in range(0, mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD - 1)}
        # Since the duplicate map votes are not counted, there aren't enough map vote requests.
        assert not voter.did_enough_players_ask_for_map_vote()
        exec_call_count = voter.squad_rcon_client.exec_command.call_count

        # Case 7: when we intentionally don't reset the map vote, the previous map votes count. Another duplicate map
        # vote still does not count.
        # This player asked previously, so adding their map vote request should not be counted.
        voter.recent_player_chat = {f'id0': player_chat_class(
            ['I have decided vote twice', '!mapvote'])}
        assert not voter.did_enough_players_ask_for_map_vote()
        # Also check that no broadcast is sent for a duplicate map vote request.
        assert voter.squad_rcon_client.exec_command.call_count == exec_call_count

        # Case 8: when we intentionally don't reset the map vote, the previous map votes count. One more new map vote
        # makes it return True now.
        # This player never asked previously, so adding their map vote request means there are enough players now.
        new_player_number = mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD + 1
        voter.recent_player_chat = {f'id{new_player_number}': player_chat_class(
            ['I have decided to add my vote', '!mapvote'])}
        assert voter.did_enough_players_ask_for_map_vote()
        # Despite the new map vote request, no broadcast is sent since the map vote has enough asks.
        assert voter.squad_rcon_client.exec_command.call_count == exec_call_count

        # NOTE(bsubei): we must reset to remove the previous map vote requests and chat.
        voter.reset_map_vote()
        voter.recent_player_chat = {}

        # Case 9: we test with a mixture of different map vote commands.
        for i in range(0, mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD + 1):
            command = random.choice(mapvoter.MAP_VOTE_COMMANDS)
            voter.recent_player_chat.update({f'id{i}': player_chat_class([command, 'random banter'])})
        assert voter.did_enough_players_ask_for_map_vote()

        # Case 10: case-insensitivity check for incoming chat commands
        voter.recent_player_chat = {
            f'id{i}': player_chat_class(['!mApvOte']) for i in range(
                0, mapvoter.NUM_PLAYERS_REQUESTING_MAP_VOTE_THRESHOLD + 1)}
        assert voter.did_enough_players_ask_for_map_vote()

    def test_did_one_clan_member_ask_for_map_vote(self, voter):
        """ Tests for did_one_clan_member_ask_for_map_vote. """
        # Some setup class for mocking PlayerChat objects.

        def chat_init(self, player_name, messages):
            self.player_name = player_name
            self.messages = messages
        player_chat_class = type('temp_player_chat', (object,), {
                                 '__init__': chat_init})

        CLAN_TAG = mapvoter.CLAN_TAG

        # Case 1: no one sends any chat at all.
        voter.recent_player_chat = {}
        assert not voter.did_one_clan_member_ask_for_map_vote()

        # Case 2: no one with a clan tag posts any chat.
        voter.recent_player_chat = {'id1': player_chat_class(
            'rando duder', ['hello friends!']), 'id2': player_chat_class('dudette', ['hai there'])}
        assert not voter.did_one_clan_member_ask_for_map_vote()

        # Case 3: some clan members post chat but not a mapvote.
        voter.recent_player_chat = {
            'id1': player_chat_class('rando duder', ['hello friends!']),
            'id2': player_chat_class(f'{CLAN_TAG} dudette', ['hai there'])}
        assert not voter.did_one_clan_member_ask_for_map_vote()

        # Case 4: a non-clan member requests a map vote.
        voter.recent_player_chat = {
            'id1': player_chat_class('rando duder', ['!mapvote']),
            'id2': player_chat_class(f'{CLAN_TAG} dudette', ['your vote does not matter'])}
        assert not voter.did_one_clan_member_ask_for_map_vote()

        # Case 5: one clan member requests a map vote (that's enough to make it return True).
        voter.recent_player_chat = {
            'id1': player_chat_class('rando duder', ['hello friends!']),
            'id2': player_chat_class(f'{CLAN_TAG} dudette', ['hai there', 'ok fine !mapvote since you said please'])}
        assert voter.did_one_clan_member_ask_for_map_vote()

        # NOTE(bsubei): we also test for missing space between clan tag and name.
        # Case 6: many clan members request a map vote.
        voter.recent_player_chat = {
            'id1': player_chat_class(f'{CLAN_TAG}duder', ['!mapvote yay']),
            'id2': player_chat_class(f'{CLAN_TAG} dudette', ['hai there', 'ok fine !mapvote since you said please'])}
        assert voter.did_one_clan_member_ask_for_map_vote()

        # Case 7: a clan member asks for a map vote (chosen from the list of map vote commands).
        command = random.choice(mapvoter.MAP_VOTE_COMMANDS)
        voter.recent_player_chat = {
            'id1': player_chat_class('rando duder', ['hello friends!']),
            'id2': player_chat_class(f'{CLAN_TAG} dudette', ['hai there', f'ok fine {command} since you said please'])}
        assert voter.did_one_clan_member_ask_for_map_vote()

        # Case 8: case-insensitivity check for incoming chat commands
        voter.recent_player_chat = {
            'id1': player_chat_class(f'{CLAN_TAG}duder', ['!mApvOtE yay']),
            'id2': player_chat_class(f'{CLAN_TAG} dudette', ['hai there', 'ok fine !maPvOte since you said please'])}
        assert voter.did_one_clan_member_ask_for_map_vote()
