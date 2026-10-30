"""
Bot d'ajout de maps : colle un code d'île (ex. 1234-5678-9012) dans #➕・add-a-map et le bot
crée sa fiche dans le forum #our-maps.

Utilisation :
    python ajout_maps.py             à laisser tourner : traite chaque code dès qu'il est posté
    python ajout_maps.py --une-fois  traite les codes en attente puis s'arrête
                                     (c'est ce que GitHub Actions lance toutes les 10 min)

L'API publique d'Epic donne le titre, le créateur et les genres ; elle ne fournit ni image
ni description. Pour en mettre, écris-les dans le même message que le code : le texte devient
la description, la 1re image jointe le visuel principal, les 3 suivantes la galerie.
Recoller le code d'une map qui a déjà sa fiche, avec un texte ou des images, met la fiche à jour.
Au démarrage, le bot traite les codes postés pendant qu'il était éteint.
Demande « Message Content Intent » (portail développeur > ton application > Bot).
DISCORD_TOKEN et GUILD_ID viennent du .env ou des variables d'environnement.
Journal : ajout_maps.log, à côté du script.
"""

import asyncio
import json
import logging
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import discord

from creer_serveur import BOUTON_JOUER, CATEGORIES, CODE_ILE, COULEUR, PIED, RAISON, lire_env

# =====================================================================
#  CONFIGURATION
# =====================================================================

# Genres de l'API Epic → tags du forum #our-maps (sans l'emoji)
TAGS = {
    "tycoon": "Tycoon",
    "pvp": "PvP", "boxfight": "PvP", "box fight": "PvP", "zonewars": "PvP", "zone wars": "PvP",
    "1v1": "PvP", "ffa": "PvP", "free for all": "PvP", "team deathmatch": "PvP",
    "gun game": "PvP", "red vs blue": "PvP",
    "party game": "Party", "party": "Party", "minigame": "Party",
    "parkour": "Parkour", "deathrun": "Parkour", "obstacle course": "Parkour",
}
TAG_NOUVEAU, TAG_MAJ = "New", "Updated"

# Réponses du bot (en anglais, comme tout le serveur)
CREEE = "✅ **{titre}** is now in {forum}: {lien}"
SANS_IMAGE = ("\n-# No image yet: post the code again with screenshots attached "
              "(the 1st one becomes the thumbnail).")
MISE_A_JOUR = "🔄 **{titre}** page updated: {lien}"
EXISTE = ("ℹ️ **{titre}** already has a page: {lien}\n"
          "-# To update it, post the code again with a new description and/or images.")
INCONNU = "❌ `{code}` isn't a published island code."
PANNE = "❌ `{code}`: something went wrong ({erreur}). Try again in a minute."

# =====================================================================

API = "https://api.fortnite.com/ecosystem/v1/islands/{}"
PAGE = "https://www.fortnite.com/@{createur}/{code}"
CODE = re.compile(r"\b\d{4}-\d{4}-\d{4}\b")
OK, ERREUR, EN_COURS = "✅", "❌", "⏳"
PORT_VERROU = 47391  # empêche de lancer le bot deux fois
DOSSIER = Path(__file__).parent

log = logging.getLogger("ajout_maps")


def nom_salon(cle):
    return next(s["nom"] for cat in CATEGORIES for s in cat["salons"] if s.get("cle") == cle)


def infos_ile(code):
    """Titre, créateur et genres de l'île, ou None si le code n'existe pas."""
    requete = urllib.request.Request(API.format(code), headers={"User-Agent": "FantastikMaps/1.0"})
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            return json.load(reponse)
    except urllib.error.HTTPError as erreur:
        if erreur.code in (400, 404):
            return None
        raise


async def trouver_fiche(forum, code):
    """Le post du forum dont la fiche porte ce code, et son premier message."""
    fils = list(forum.threads) + [fil async for fil in forum.archived_threads(limit=100)]
    for fil in fils:
        try:
            premier = fil.starter_message or await fil.fetch_message(fil.id)
        except discord.NotFound:
            continue
        if any(code in champ.value for embed in premier.embeds for champ in embed.fields):
            return fil, premier
    return None, None


def reattacher(embed, pieces):
    """Une image déjà jointe au message se renvoie en attachment://, pas par son lien."""
    if embed.image.url:
        lien = embed.image.url.split("?")[0]
        for piece in pieces:
            if piece.url.split("?")[0] == lien:
                embed.set_image(url=f"attachment://{piece.filename}")
    return embed


def galerie(page, fichiers):
    # Des embeds qui partagent la même URL s'affichent en galerie d'images
    return [discord.Embed(url=page).set_image(url=f"attachment://{f.filename}")
            for f in fichiers[1:4]]


def tags_forum(forum, noms):
    return [t for t in forum.available_tags if t.name in noms][:5]


async def creer_fiche(forum, infos, description, fichiers):
    guild = forum.guild
    code = infos["code"]
    page = PAGE.format(createur=infos["creatorCode"], code=code)
    genres = " · ".join(t.title() for t in infos.get("tags", []))
    icone = guild.icon.url if guild.icon else None

    fiche = discord.Embed(title=infos["title"], description=description[:4096],
                          colour=COULEUR, url=page)
    fiche.add_field(name=CODE_ILE, value=f"`{code}`")
    if genres:
        fiche.add_field(name="🎮 Genre", value=genres)
    if icone:
        fiche.set_thumbnail(url=icone)
    fiche.set_footer(text=f"{guild.name} • {PIED}", icon_url=icone)
    if fichiers:
        fiche.set_image(url=f"attachment://{fichiers[0].filename}")

    vue = discord.ui.View()
    vue.add_item(discord.ui.Button(label=BOUTON_JOUER, emoji="▶️", url=page))
    noms = {TAG_NOUVEAU} | {TAGS[t] for t in infos.get("tags", []) if t in TAGS}
    fil, _ = await forum.create_thread(name=infos["title"][:100], applied_tags=tags_forum(forum, noms),
                                       embeds=[fiche, *galerie(page, fichiers)], files=fichiers,
                                       view=vue, reason=RAISON)
    return fil


async def mettre_a_jour(fil, premier, page, description, fichiers):
    if fil.archived:  # les posts inactifs s'archivent et ne se modifient plus
        await fil.edit(archived=False)
    principal = premier.embeds[0]
    if description:
        principal.description = description[:4096]
    if fichiers:
        principal.set_image(url=f"attachment://{fichiers[0].filename}")
        await premier.edit(embeds=[principal, *galerie(page, fichiers)], attachments=fichiers)
    else:
        await premier.edit(embeds=[reattacher(e, premier.attachments) for e in premier.embeds])
    noms = {t.name for t in fil.applied_tags} - {TAG_NOUVEAU} | {TAG_MAJ}
    await fil.edit(applied_tags=tags_forum(fil.parent, noms))


async def publier_map(forum, code, description="", fichiers=()):
    """Crée ou met à jour la fiche de la map, et renvoie la réponse à afficher."""
    fichiers = list(fichiers)
    infos = await asyncio.to_thread(infos_ile, code)
    if infos is None:
        return False, INCONNU.format(code=code)
    page = PAGE.format(createur=infos["creatorCode"], code=code)
    fil, premier = await trouver_fiche(forum, code)
    if fil is None:
        fil = await creer_fiche(forum, infos, description, fichiers)
        log.info("Fiche créée : %s (%s)", infos["title"], code)
        texte = CREEE.format(titre=infos["title"], forum=forum.mention, lien=fil.jump_url)
        return True, texte + ("" if fichiers else SANS_IMAGE)
    if premier.author.id == forum.guild.me.id and (description or fichiers):
        await mettre_a_jour(fil, premier, page, description, fichiers)
        log.info("Fiche mise à jour : %s (%s)", fil.name, code)
        return True, MISE_A_JOUR.format(titre=fil.name, lien=fil.jump_url)
    return True, EXISTE.format(titre=fil.name, lien=fil.jump_url)


async def traiter(message, forum):
    codes = list(dict.fromkeys(CODE.findall(message.content)))
    if not codes:
        return
    await message.add_reaction(EN_COURS)
    # Le texte et les images ne vont à la fiche que s'il n'y a qu'un seul code dans le message
    description, fichiers = "", []
    if len(codes) == 1:
        description = CODE.sub("", message.content).strip()
        images = [a for a in message.attachments if (a.content_type or "").startswith("image/")]
        fichiers = [await a.to_file(filename=f"image_{i}{Path(a.filename).suffix.lower()}")
                    for i, a in enumerate(images[:4])]

    reponses, tout_ok = [], True
    for code in codes:
        try:
            ok, texte = await publier_map(forum, code, description, fichiers)
        except (discord.HTTPException, urllib.error.URLError, OSError) as erreur:
            log.exception("Échec pour %s", code)
            ok, texte = False, PANNE.format(code=code, erreur=type(erreur).__name__)
        tout_ok &= ok
        reponses.append(texte)

    await message.reply("\n".join(reponses), mention_author=False, suppress_embeds=True)
    await message.remove_reaction(EN_COURS, message.guild.me)
    await message.add_reaction(OK if tout_ok else ERREUR)


def deja_traite(message):
    return any(r.me and str(r.emoji) in (OK, ERREUR) for r in message.reactions)


def main():
    journal = [logging.FileHandler(DOSSIER / "ajout_maps.log", encoding="utf-8")]
    if sys.stdout:  # pas de console avec pythonw
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        journal.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", handlers=journal)
    logging.getLogger("discord").setLevel(logging.WARNING)

    verrou = socket.socket()
    try:
        verrou.bind(("127.0.0.1", PORT_VERROU))
    except OSError:
        sys.exit("Le bot tourne déjà.")

    env = {**lire_env(DOSSIER / ".env"),
           **{k: v for k, v in os.environ.items() if k in ("DISCORD_TOKEN", "GUILD_ID")}}
    une_fois = "--une-fois" in sys.argv
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    salons = {}
    file_attente = asyncio.Lock()  # une map à la fois, pour ne jamais créer de doublon

    @client.event
    async def on_ready():
        try:
            guild = client.get_guild(int(env["GUILD_ID"]))
            salons["ajout"] = discord.utils.get(guild.text_channels, name=nom_salon("ajout_maps"))
            salons["maps"] = discord.utils.get(guild.forums, name=nom_salon("maps"))
            if not all(salons.values()):
                log.error("Salon d'ajout ou forum introuvable : relance creer_serveur.py.")
                return
            log.info("Prêt : colle un code dans #%s", salons["ajout"].name)
            # Rattrape les codes postés pendant que le bot était éteint
            async with file_attente:
                async for message in salons["ajout"].history(limit=100, oldest_first=True):
                    if not message.author.bot and not deja_traite(message):
                        await traiter(message, salons["maps"])
        finally:
            if une_fois:
                await client.close()

    @client.event
    async def on_message(message):
        if message.author.bot or message.channel != salons.get("ajout"):
            return
        async with file_attente:
            await traiter(message, salons["maps"])

    try:
        client.run(env["DISCORD_TOKEN"], log_handler=None)
    except discord.PrivilegedIntentsRequired:
        sys.exit("Active « Message Content Intent » dans le portail développeur "
                 "(ton application > Bot), puis relance.")


if __name__ == "__main__":
    main()
