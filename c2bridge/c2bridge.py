"""C2-Brücke: verbindet Discord-Kanäle mit Gruppen-Chats der SIDC-C2-Seite.

Der Bot ruft ausschließlich die Seite an (Polling + POST) – die Seite muss den Bot nie erreichen.

* Seite -> Discord: Der Bot holt neue Chat-Nachrichten aus der Outbox und schreibt sie in den Kanal.
* Discord -> Seite: Nachrichten in verbundenen Kanälen werden an die Seite geschickt. Wer sein Konto per
  ``/c2 link CODE`` verknüpft hat, erscheint dort unter dem eigenen Namen, alle anderen als „Name (Discord)".
"""
from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
import discord
from redbot.core import Config, commands

log = logging.getLogger("red.c2bridge")

PROVIDER = "discord"
OUTBOX_INTERVAL = 2.0
LINKS_INTERVAL = 30.0
CHANNELS_INTERVAL = 120.0
MAX_MSG = 1900  # Discord erlaubt 2000 Zeichen


def _chunks(text: str, size: int = MAX_MSG) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


class C2Bridge(commands.Cog):
    """Brücke zwischen Discord-Kanälen und SIDC-C2-Gruppenchats."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5C2B41D6E, force_registration=True)
        self.config.register_global(url="", token="")
        self._session: aiohttp.ClientSession | None = None
        self._linked: set[int] = set()
        self._tasks: list[asyncio.Task] = []

    # ── Lebenszyklus ─────────────────────────────────────────────────────────

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self._tasks = [
            asyncio.create_task(self._outbox_loop()),
            asyncio.create_task(self._links_loop()),
            asyncio.create_task(self._channels_loop()),
            asyncio.create_task(self._enable_slash()),
        ]

    async def _enable_slash(self) -> None:
        """Schaltet /c2 automatisch frei (sonst manuell: [p]slash enablecog c2bridge + [p]slash sync)."""
        await self.bot.wait_until_ready()
        try:
            self.bot.enable_app_command("c2")
            await self.bot.tree.sync()
        except Exception:  # noqa: BLE001 - dann bleibt der Textbefehl [p]c2 link CODE
            log.warning("Slash-Befehl /c2 konnte nicht automatisch aktiviert werden – siehe README.", exc_info=True)

    async def cog_unload(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self._session:
            await self._session.close()

    # ── API zur Seite ────────────────────────────────────────────────────────

    async def _api(self, method: str, path: str, **kw) -> tuple[int, object]:
        # Im Docker-Stack kommen Adresse und Token aus der Umgebung; per Befehl gesetzte Werte haben Vorrang.
        url = ((await self.config.url()) or os.environ.get("C2_URL", "")).rstrip("/")
        token = (await self.config.token()) or os.environ.get("C2_TOKEN", "")
        if not url or not token or self._session is None:
            return 0, None
        try:
            async with self._session.request(method, url + path, headers={"Authorization": f"Bearer {token}"}, **kw) as r:
                try:
                    data = await r.json(content_type=None)
                except Exception:  # noqa: BLE001
                    data = None
                return r.status, data
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return 0, None

    # ── Seite -> Discord ─────────────────────────────────────────────────────

    async def _outbox_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                status, items = await self._api("GET", "/bridge/outbox", params={"provider": PROVIDER})
                if status == 200 and isinstance(items, list) and items:
                    done: list[str] = []
                    refs: dict[str, str] = {}
                    for i in items:
                        ok, mid = await self._deliver(i)
                        if ok:
                            done.append(i["id"])
                            if mid:
                                refs[i["id"]] = str(mid)
                    if done:
                        await self._api("POST", "/bridge/outbox/ack", json={"ids": done, "refs": refs})
                await asyncio.sleep(OUTBOX_INTERVAL if status == 200 else 10)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Outbox-Lauf fehlgeschlagen")
                await asyncio.sleep(10)

    async def _deliver(self, item: dict) -> tuple[bool, int | None]:
        """(erledigt, ID der gesendeten Nachricht). erledigt=True auch bei dauerhaft unerreichbarem Ziel,
        False = später erneut versuchen."""
        try:
            cid = int(item["channel_id"])
        except (KeyError, ValueError):
            return True, None
        if item.get("kind") == "dm":  # Direktnachricht an einen verknüpften Nutzer (channel_id = Discord-Nutzer-ID)
            try:
                user = self.bot.get_user(cid) or await self.bot.fetch_user(cid)
                first = None
                for part in _chunks(item.get("text", "")):
                    sent = await user.send(part, allowed_mentions=discord.AllowedMentions.none())
                    first = first or sent.id
                return True, first
            except (discord.NotFound, discord.Forbidden):
                return True, None  # Nutzer unbekannt oder DMs gesperrt – nicht endlos wiederholen
            except discord.HTTPException:
                return False, None
        channel = self.bot.get_channel(cid)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(cid)
            except (discord.NotFound, discord.Forbidden):
                return True, None
            except discord.HTTPException:
                return False, None
        text = f"**{item.get('author') or '?'}:** {item.get('text', '')}"
        try:
            for part in _chunks(text):
                await channel.send(part, allowed_mentions=discord.AllowedMentions.none())
            return True, None
        except discord.Forbidden:
            return True, None
        except discord.HTTPException:
            return False, None

    # ── Discord -> Seite ─────────────────────────────────────────────────────

    async def _links_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                status, ids = await self._api("GET", "/bridge/links", params={"provider": PROVIDER})
                if status == 200 and isinstance(ids, list):
                    self._linked = {int(i) for i in ids if str(i).isdigit()}
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Link-Abgleich fehlgeschlagen")
            await asyncio.sleep(LINKS_INTERVAL)

    async def _channels_loop(self) -> None:
        """Meldet alle Textkanäle, in denen der Bot lesen und schreiben darf – Auswahlliste im Admin-Bereich der Seite."""
        await self.bot.wait_until_ready()
        while True:
            try:
                channels = [
                    {"id": str(ch.id), "name": ch.name, "group_id": str(g.id), "group_name": g.name}
                    for g in self.bot.guilds
                    for ch in g.text_channels
                    if g.me is not None and ch.permissions_for(g.me).view_channel and ch.permissions_for(g.me).send_messages
                ][:5000]
                await self._api("POST", "/bridge/channels", json={"provider": PROVIDER, "channels": channels})
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Kanalliste konnte nicht gemeldet werden")
            await asyncio.sleep(CHANNELS_INTERVAL)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            await self._handle_dm(message)
            return
        if message.channel.id not in self._linked:
            return
        text = message.clean_content
        if message.attachments:
            text += "\n" + "\n".join(a.url for a in message.attachments)
        if not text.strip():
            return
        status, _ = await self._api(
            "POST",
            "/bridge/inbound",
            json={
                "provider": PROVIDER,
                "channel_id": str(message.channel.id),
                "author_id": str(message.author.id),
                "author_name": message.author.display_name,
                "text": text,
            },
        )
        if status == 404:  # Kanal wurde auf der Seite getrennt
            self._linked.discard(message.channel.id)

    async def _handle_dm(self, message: discord.Message) -> None:
        """Antwort auf eine Benachrichtigungs-DM: Der Nutzer nutzt „Antworten“ auf die Nachricht des Bots."""
        ref = message.reference
        if ref is None or not ref.message_id:
            await message.channel.send(
                "Um auf eine Benachrichtigung zu antworten, nutze bei der Nachricht „Antworten“ (Rechtsklick bzw. lange drücken)."
            )
            return
        status, data = await self._api(
            "POST",
            "/bridge/dm-reply",
            json={
                "provider": PROVIDER,
                "author_id": str(message.author.id),
                "reply_to": str(ref.message_id),
                "text": message.clean_content,
            },
        )
        if status == 200:
            try:
                await message.add_reaction("✅")
            except discord.HTTPException:
                pass
        else:
            detail = data.get("detail") if isinstance(data, dict) else None
            await message.channel.send(f"Antwort nicht übermittelt: {detail or 'Die C2-Seite ist nicht erreichbar.'}")

    # ── Befehle ──────────────────────────────────────────────────────────────

    @commands.hybrid_group(name="c2")
    async def c2(self, ctx: commands.Context) -> None:
        """SIDC-C2: Konto oder Kanal verbinden."""

    @c2.command(name="link")
    async def c2_link(self, ctx: commands.Context, code: str) -> None:
        """Code von der C2-Seite einlösen (verbindet dein Konto bzw. diesen Kanal)."""
        code = code.strip().upper()
        # Discord verlangt binnen 3 s eine Rückmeldung; der Aufruf an die Seite kann länger dauern.
        await ctx.defer(ephemeral=True)
        if ctx.interaction is None:
            # Als Textbefehl wäre der Code öffentlich sichtbar – entfernen (er ist ohnehin einmalig).
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        channel_id = str(ctx.channel.id) if ctx.guild else None
        status, data = await self._api(
            "POST",
            "/bridge/claim",
            json={"provider": PROVIDER, "code": code, "author_id": str(ctx.author.id), "channel_id": channel_id},
        )
        if status == 0:
            msg = "Die C2-Seite ist nicht erreichbar (oder der Bot ist nicht eingerichtet)."
        elif status == 200 and isinstance(data, dict):
            if data.get("kind") == "conv":
                msg = f"Kanal verbunden mit dem Chat „{data.get('label', '')}“."
                self._linked.add(ctx.channel.id)
            else:
                msg = f"Dein Discord-Konto ist jetzt mit **{data.get('label', '')}** auf der C2-Seite verbunden."
        else:
            detail = data.get("detail") if isinstance(data, dict) else None
            msg = f"Fehlgeschlagen: {detail or status}"
        await ctx.send(msg, ephemeral=True)

    @commands.group(name="c2bridge")
    @commands.is_owner()
    async def c2bridge(self, ctx: commands.Context) -> None:
        """Einrichtung der C2-Brücke (nur Bot-Besitzer)."""

    @c2bridge.command(name="url")
    async def c2bridge_url(self, ctx: commands.Context, url: str) -> None:
        """Adresse der C2-Seite setzen, z. B. https://c2.example.org"""
        await self.config.url.set(url.rstrip("/"))
        await ctx.tick()

    @c2bridge.command(name="token")
    async def c2bridge_token(self, ctx: commands.Context, token: str) -> None:
        """Brücken-Token (BRIDGE_TOKEN der Seite) setzen. Die Nachricht wird gelöscht."""
        await self.config.token.set(token)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send("Token gespeichert.", delete_after=5)

    @c2bridge.command(name="status")
    async def c2bridge_status(self, ctx: commands.Context) -> None:
        """Verbindung zur Seite prüfen."""
        status, ids = await self._api("GET", "/bridge/links", params={"provider": PROVIDER})
        if status == 200:
            await ctx.send(f"Verbunden. {len(ids)} Kanal/Kanäle verknüpft.")
        elif status == 401:
            await ctx.send("Die Seite lehnt das Token ab (BRIDGE_TOKEN prüfen).")
        else:
            await ctx.send("Die Seite ist nicht erreichbar oder URL/Token fehlen.")
