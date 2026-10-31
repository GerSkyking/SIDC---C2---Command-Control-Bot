#!/bin/sh
# Richtet beim ersten Start eine Red-Instanz ein und startet den Bot mit dem c2bridge-Cog.
#   DISCORD_TOKEN     Bot-Token (Pflicht – ohne bleibt der Container untätig)
#   C2_URL / C2_TOKEN Adresse und BRIDGE_TOKEN der C2-Seite
#   DISCORD_OWNER_ID  optional: Discord-ID des Bot-Besitzers (sonst der Besitzer der Discord-Anwendung)
#   BOT_PREFIX        optional: Textbefehl-Präfix (Standard !)
set -e

NAME=c2

if [ -z "$DISCORD_TOKEN" ]; then
  echo "DISCORD_TOKEN ist nicht gesetzt - der Discord-Bot bleibt inaktiv."
  exec sleep infinity
fi

CFG="$HOME/.config/Red-DiscordBot/config.json"
if ! grep -q "\"$NAME\"" "$CFG" 2>/dev/null; then
  redbot-setup --no-prompt --instance-name "$NAME" --data-path /data --backend json
fi

# Cog bei jedem Start aus dem Image übernehmen, damit Updates ankommen.
COGS=/data/cogs/CogManager/cogs
mkdir -p "$COGS"
rm -rf "$COGS/c2bridge"
cp -r /opt/c2bridge "$COGS/c2bridge"

if [ -n "$DISCORD_OWNER_ID" ]; then
  exec redbot "$NAME" --token "$DISCORD_TOKEN" --prefix "${BOT_PREFIX:-!}" --no-prompt --owner "$DISCORD_OWNER_ID" --load-cogs c2bridge
fi
exec redbot "$NAME" --token "$DISCORD_TOKEN" --prefix "${BOT_PREFIX:-!}" --no-prompt --load-cogs c2bridge
