# C2-DC_Bot

[Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot)-Cog für **SIDC – C2 – Command & Control**.
Der Cog `c2bridge` verbindet Discord-Kanäle mit Gruppen-Chats der Seite:

- Nachrichten der Seite erscheinen im Discord-Kanal (`**Name:** Text`).
- Nachrichten im Discord-Kanal erscheinen im Chat der Seite – unter dem eigenen Namen, wenn das Konto verknüpft ist,
  sonst als `Name (Discord)`.
- Der Bot ruft nur die Seite an (Polling alle 2 s). Die Seite muss den Bot nie erreichen; der Bot kann irgendwo laufen.

## Betrieb im Docker-Stack der C2-Seite (empfohlen)

Der Bot ist als Dienst `discord-bot` im `docker-compose.yml` der C2-Seite eingebunden und wird beim `docker compose up -d --build`
direkt aus diesem Repo gebaut. In der `.env` der C2-Seite genügen:

```
BRIDGE_TOKEN=<langer Zufallswert>
DISCORD_TOKEN=<Bot-Token aus dem Developer Portal>
# optional: DISCORD_OWNER_ID, BOT_PREFIX
```

Der Container richtet Red beim ersten Start selbst ein, lädt den Cog, nimmt Adresse (`http://backend:8080`) und Token aus der
Umgebung und aktiviert `/c2` automatisch. Ohne `DISCORD_TOKEN` bleibt er untätig. Wichtig: im Developer Portal unter *Bot* den
**Message Content Intent** einschalten und den Bot mit Lese-/Schreibrechten einladen. Die manuelle Einrichtung unten ist dann nicht nötig.

## Einrichtung ohne Docker

1. **Discord-Anwendung** im [Developer Portal](https://discord.com/developers/applications) anlegen, Bot erzeugen,
   unter *Bot* den **Message Content Intent** aktivieren. Einladen mit den Rechten *Nachrichten lesen/senden*.
2. **Red** installieren (siehe Red-Doku, Python 3.11) und den Bot mit dem Token starten.
3. **Cog installieren** (Pfad zum Repo bzw. GitHub-URL anpassen):
   ```
   [p]repo add c2bot <URL-oder-lokaler-Pfad>
   [p]cog install c2bot c2bridge
   [p]load c2bridge
   ```
4. **Seite verbinden** – `BRIDGE_TOKEN` in der `.env` der C2-Seite setzen (langer Zufallswert), dann im Discord (nur Bot-Besitzer):
   ```
   [p]c2bridge url https://c2.example.org
   [p]c2bridge token <BRIDGE_TOKEN>
   [p]c2bridge status
   ```
5. **Slash-Befehle** aktivieren: `[p]slash enablecog c2bridge`, dann `[p]slash sync`.

## Benutzung

- **Konto verknüpfen:** Auf der Seite *Einstellungen → Benachrichtigungen → Discord verknüpfen* einen Code erzeugen und in
  Discord `/c2 link CODE` ausführen (der Slash-Befehl ist nur für dich sichtbar).
- **Kanal verbinden:** Im Gruppen-Chat der Seite *Mit Discord verbinden* wählen (nur Ersteller/Admin), Code erzeugen und im
  gewünschten Discord-Kanal `/c2 link CODE` ausführen.
- Verbindungen lassen sich auf der Seite wieder lösen.

## Hinweise

- Codes sind 15 Minuten gültig und einmalig.
- Erwähnungen (`@name`) in Discord werden von der Seite wie im Web-Chat aufgelöst und lösen Benachrichtigungen aus.
- Bearbeiten/Löschen wird nicht synchronisiert; Anhänge kommen als Link an.
- Red steht unter GPL-3.0; für dieses Repo ist daher dieselbe Lizenz die einfachste Wahl.
