#! /usr/bin/env python3
# Copyright (C) 2020 Basheer Subei
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
# A script/bot that interacts with a Squad server through a Squad RCON client.
#

import argparse
from datetime import datetime
from pathlib import Path
import time
import logging

from srcds import rcon
from mapvoter import mapvoter

logger = logging.getLogger()

# The default port for RCON.
DEFAULT_PORT = 21114

# How long to sleep in between each "has the map changed" check (in seconds).
SLEEP_BETWEEN_MAP_CHECKS_S = 10.0


def parse_cli():
    """ Parses sys.argv (commandline args) and returns a parser with the arguments. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--rcon-address', required=True,
                        help='The address to the RCON server (IP or URL).')
    parser.add_argument('--rcon-port', type=int, help=f'The port for the RCON server. Defaults to {DEFAULT_PORT}.',
                        default=DEFAULT_PORT)
    parser.add_argument('--rcon-password', required=True,
                        help='The password for the RCON server.')
    parser.add_argument('--voting-cooldown', type=float,
                        help=('How long to wait (in seconds) in between map votes. Defaults to '
                              f'{mapvoter.DEFAULT_VOTING_COOLDOWN_S}.'), default=mapvoter.DEFAULT_VOTING_COOLDOWN_S)
    parser.add_argument('--voting-duration', type=float,
                        help=('How long to listen for votes in seconds. Defaults to '
                              f'{mapvoter.DEFAULT_VOTING_TIME_DURATION_S}.'),
                        default=mapvoter.DEFAULT_VOTING_TIME_DURATION_S)
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                        help='Verbose flag to indicate that DEBUG level output should be logged.')
    parser.add_argument('--map-rotation-filepath',
                        help=('The filepath to the map rotation. If specified, the mapvoting choices will include the '
                              'next maps in the rotation. If unspecified, the choices will be a random set of maps '
                              'from the provided map layers JSON file.'))
    parser.add_argument('--map-layers-url', default=mapvoter.DEFAULT_LAYERS_URL,
                        help=('The URL to the map layers JSON file containing all map layers to use for the map vote '
                              'choices if a map rotation is not provided/used.'))
    return parser.parse_args()


def setup_logger(verbose):
    """ Sets up the logger based on the verbosity level. """
    level = logging.DEBUG if verbose else logging.INFO

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    ch.setLevel(level)

    # Create a directory to store the log files in.
    log_dir = Path.cwd() / 'logs'
    Path.mkdir(log_dir, exist_ok=True)
    log_filename = log_dir / datetime.now().isoformat().replace('.',
                                                                '_').replace(':', '_')
    fh = logging.FileHandler(log_filename)

    logger.setLevel(level)
    logger.addHandler(ch)
    logger.addHandler(fh)


# TODO(bsubei): create a plugin abstract class that voter (and more stuff I make) implement and get called here.
def connect_and_run_plugins(args):
    # Set up the connection to RCON using a managed context (socket is closed automatically once we leave this context).
    with rcon.get_managed_rcon_connection(args.rcon_address, port=args.rcon_port, password=args.rcon_password) as conn:
        # Initialize the mapvoter.
        voter = mapvoter.MapVoter(
            conn, args.voting_cooldown, args.voting_duration)

        logger.info(f'Will start checking for new map every {SLEEP_BETWEEN_MAP_CHECKS_S} seconds and waiting to start '
                    'a map vote...')

        # Get the current map at start so we know when the map changes.
        current_map, next_map = voter.squad_rcon_client.get_current_and_next_map()

        # Spin until we're done, but do it slowly.
        while True:
            current_map, next_map = voter.squad_rcon_client.get_current_and_next_map()
            logger.debug(f'Current map: {current_map}, next map: {next_map}')

            # Get most recent player messages since we last asked for the current map.
            recent_player_chat = conn.get_player_chat()
            conn.clear_player_chat()

            voter.run_once(
                current_map, next_map, recent_player_chat,
                map_rotation_filepath=args.map_rotation_filepath,
                map_layers_url=args.map_layers_url
            )

            time.sleep(SLEEP_BETWEEN_MAP_CHECKS_S)


def main():
    """ Run the RCON bot script. """
    print('Starting up rconbot script!')
    args = parse_cli()

    # Set up the logger.
    setup_logger(args.verbose)

    # Connect to RCON server and run plugins, and if you fail keep retrying (does not swallow keyboard interrupts).
    while True:
        try:
            connect_and_run_plugins(args)
        except Exception as e:
            logger.error(f'Encountered error: {e}. Retrying...')
        time.sleep(10.0)


if __name__ == '__main__':
    main()
