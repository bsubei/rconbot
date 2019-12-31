# What is this?
This repo contains a collection of tools and scripts to be used to remotely control (RCON) a Squad server (*currently just a mapvoter script*). The RCON client used is a modified version of [pysrcds](https://github.com/bsubei/pysrcds).

# What is Squad?
See [the official website](https://joinsquad.com/) for information on Squad.

# Planned feature list (not in any particular order)
- [X] Add map voting to a server. Users can start a mapvote in text chat, and the bot (this tool) sends text chat to all users and offers options on maps to vote on (voting happens in-game). The map with the highest vote is set as the next map. In the event of the tool failing or not running, the original map rotation takes over (defined in a config file).
- [ ] Having multiple map rotations based on some event (e.g. when player count is low, switch to seeding rotation). This feature will require this bot to handle the map rotations entirely and set next map every time (ignoring the default map rotation config file).
- [ ] A team shuffle command (optionally add the ability to vote for this).
- [ ] A team swap command that swaps both teams completely (useful for competitive servers).
- [ ] The ability to set which team joining players will be assigned to based on clan tags (also useful for competitive servers).
- [ ] (Very ambitious) some kind of team balance feature that perhaps triggers a team shuffle when the previous game was lopsided (using tickets, probably depends on mode). There's a lot of potential for these ideas, but it depends on what data is available through RCON.
- [ ] Automatically give whitelist to seeders/regulars who put in enough hours.
- [ ] The ability for players to ping an admin on Discord if no admin is available on the server.
- [ ] A trivia questions bot to keep seeding servers more interesting for players, possibly with rewards (whitelist for best players).
- [ ] Seeding bot that posts the rules every X minutes and announces when the server is live.
- [ ] A polling bot so we can get direct feedback on polls/questions from in-game players (can also store player vote metadata, e.g. how many hours they've played on the server so we can see what regulars vs. randoms think).
- [ ] in-game chat mortar calculator. Player types origin and target coordinates in team chat, and gets the bearing and angle as an admin warning (only they can see it).

# Map Voter current features:
- Players with the specified clan tag can start a map vote at any time by typing a valid command in chat (e.g. `!mapvote`).
- Players without the clan tag can *ask* for a map vote by typing in the same command. When enough players ask for it (default 5), a map vote is started *if the cooldown is over*.
- If the map rotation file is provided, the candidate maps are the next four maps in the rotation.
- Otherwise, a random set of maps is chosen based on the [squad\_map\_randomizer](https://github.com/bsubei/squad_map_randomizer) tool.

# Resources needed to develop this.
- The RCON protocol used by Squad servers is based off of [Valve's RCON protocol](https://developer.valvesoftware.com/wiki/Source_RCON_Protocol), with minor modifications (for handling Unicode and multi-packet messages). See [SQUAD RCON](https://discord.gg/8tpbYZK) Discord group for more support.
- The list of RCON allowed commands are found [in the wiki](https://squad.gamepedia.com/Server_Administration).

# Python version and testing.
I used Python 3.6.8 to write this, and used pytest (the python3 version) to run the tests. Just use `python3 -m pytest`
in the root directory to run the unit tests. Auto-linting is done using `autopep8 --in-place <filename>`.

# Installation
Run `pip3 install -r requirements.txt` to install the packages locally into the `src/` folder, then you can run the mapvoter script. Example usage: `python3 mapvoter/mapvoter.py --rcon-address '123.456.789.123' --rcon-port 12345 --rcon-password myfancypass --voting-delay 900 --voting-duration 60 --verbose`.

# License
The license is GPLv3. Please see the LICENSE file.
