# Hack Let Loose - Language Skill Check Bot

## Create an API-Key in your CRCON
It needs the following permissions:
- `get_detailed_players`
- `get_historical_logs`
- `message_player`
- `kick` player
- `punish` player
- `flag_player`

## Installation
We need docker, docker-compose and git installed on your system.
- `git clone https://github.com/element-code/hll-language-skill-check.git`
- `cd hll-language-skill-check`
- `git fetch --tags && git checkout $(git tag -l --contains HEAD --sort -v:refname | head -n1)`
- `cp words.dist.json words.json`
- `cp dist.env .env`
- Edit the `.env` file to your needs `nano .env`.
- `docker compose up --detach --build`

## Configuration
When you change the configuration, you need to restart the containers:
- `docker-compose down`
- `docker-compose up -d --build`

### Defaults
In the `.env` set some defaults:
- Set your Timezone: `TZ=Europe/Berlin`
- Set your Servers API base url and API key, up to 10 servers are supported
- Configure messages and `words.json`

#### Debugging
If something doesn't work as expected, give it a few minutes to resolve.
- Did you restart the containers after changing the configuration?
- Check the logs of the checker: `docker logs hll-language-skill-check-checker-1`

## Updates
- `cd hll-language-skill-check`
- `git fetch --tags && git checkout $(git tag -l --contains HEAD --sort -v:refname | head -n1)`
- `docker compose up --detach --build`
