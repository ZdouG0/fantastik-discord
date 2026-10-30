"""
Met en place un serveur Discord (en anglais) qui sert de vitrine à nos maps Fortnite (UEFN) :
rôles, catégories, salons, forums, permissions, AutoMod, mode communauté,
questionnaire d'arrivée (Onboarding) et messages d'accueil.

Utilisation :
    python creer_serveur.py                       crée / met à jour le serveur
    python creer_serveur.py --apercu              affiche la structure sans rien toucher
    python creer_serveur.py --supprimer-defauts   supprime aussi les salons "général"
                                                  créés par Discord (serveur neuf seulement)
    python creer_serveur.py --fondateurs          donne le rôle Founder à TOUS les membres
                                                  présents (à ne lancer qu'une fois ; demande
                                                  "Server Members Intent" sur le portail)

Le script peut être relancé sans risque : ce qui existe déjà (même nom, ou ancien nom
indiqué par "ancien") est réutilisé, renommé si besoin et mis à jour. Il ne supprime que
des salons vides (ou ne contenant que ses propres messages) qui ont été remplacés, et les
rôles listés dans ANCIENS_ROLES.
Le token du bot et l'ID du serveur se mettent dans le fichier .env (voir .env.example).
"""

import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

import discord

# =====================================================================
#  CONFIGURATION — modifie librement tout ce qui suit
#  (tout ce qui est affiché sur le serveur est en anglais)
# =====================================================================

COULEUR = 0x9B59B6  # couleur des messages du bot
RAISON = "Server setup"  # visible dans les logs d'audit
PIED = "Fortnite Maps"  # bas des messages : "<nom du serveur> • Fortnite Maps"
DESCRIPTION = "The home of our Fortnite maps: island codes, new releases, betas and community events."
LANGUE = discord.Locale.american_english  # langue principale du serveur

# Rôles, du plus haut au plus bas. "cle" sert à y faire référence plus bas,
# "ancien" = ancien nom, pour renommer le rôle au lieu d'en créer un nouveau.
# Les rôles des autres bots sont rangés automatiquement juste sous les modérateurs.
ROLES = [
    {"cle": "fondateur", "nom": "👑 Founder", "ancien": "👑 Fondateur", "couleur": 0xF1C40F,
     "separe": True, "perms": {"administrator": True}},
    {"cle": "modo", "nom": "🛡️ Moderator", "ancien": "🛡️ Modérateur", "couleur": 0xE74C3C,
     "separe": True,
     "perms": {"manage_messages": True, "manage_threads": True, "kick_members": True,
               "ban_members": True, "moderate_members": True, "mute_members": True,
               "deafen_members": True, "move_members": True, "manage_nicknames": True,
               "view_audit_log": True, "mention_everyone": True}},
    {"cle": "createur", "nom": "🛠️ Map Creator", "ancien": "🛠️ Créateur de maps",
     "couleur": 0x9B59B6, "separe": True, "perms": {"mention_everyone": True}},
    {"cle": "testeur", "nom": "🧪 Tester", "ancien": "🧪 Testeur", "couleur": 0x2ECC71,
     "separe": True},
    {"cle": "contenu", "nom": "🎥 Content Creator", "ancien": "🎥 Créateur de contenu",
     "couleur": 0xE91E63, "separe": True},
    # Rôles de niveau, donnés automatiquement par Arcane quand on atteint le "niveau"
    {"cle": "lvl_recrue", "nom": "🪂 Rookie", "ancien": "🪂 Recrue", "couleur": 0xBDC3C7,
     "niveau": 2},
    {"cle": "lvl_batisseur", "nom": "🔨 Builder", "ancien": "🔨 Bâtisseur", "couleur": 0x5DADE2,
     "niveau": 5},
    {"cle": "lvl_sweaty", "nom": "⚡ Sweaty", "couleur": 0x00D2D3, "niveau": 10},
    {"cle": "lvl_pro", "nom": "🎯 Pro", "couleur": 0x5865F2, "niveau": 20},
    {"cle": "lvl_legende", "nom": "🏆 Legend", "ancien": "🏆 Légende", "couleur": 0xFFD43B,
     "niveau": 35},
    # Seuls les modos et créateurs de maps peuvent pinger ces rôles (mention_everyone)
    {"cle": "notif_maps", "nom": "🔔 Map Alerts", "ancien": "🔔 Notif Maps"},
    {"cle": "notif_events", "nom": "🔔 Event Alerts", "ancien": "🔔 Notif Events"},
    {"cle": "pc", "nom": "💻 PC"},
    {"cle": "playstation", "nom": "🎮 PlayStation"},
    {"cle": "xbox", "nom": "🟢 Xbox"},
    {"cle": "switch", "nom": "🔴 Switch"},
    {"cle": "mobile", "nom": "📱 Mobile"},
]

# Rôles d'une ancienne version du script, supprimés s'ils existent encore
ANCIENS_ROLES = ["🤝 Co-fondateur"]

# Profils d'accès. "everyone" = tout le monde, "bots" = les bots ajoutés au serveur,
# sinon la "cle" d'un rôle. Le profil d'une catégorie s'applique à ses salons,
# celui d'un salon s'y ajoute.
ACCES = {
    "lecture_seule": {
        "everyone": {"send_messages": False, "create_public_threads": False,
                     "create_private_threads": False},
        "modo": {"send_messages": True},
        "createur": {"send_messages": True},
        "bots": {"send_messages": True},
    },
    "vitrine_contenu": {
        "everyone": {"send_messages": False},
        "contenu": {"send_messages": True},
        "modo": {"send_messages": True},
    },
    "beta": {
        "everyone": {"view_channel": False},
        "testeur": {"view_channel": True},
        "createur": {"view_channel": True},
        "modo": {"view_channel": True},
    },
    "equipe": {
        "everyone": {"view_channel": False},
        "createur": {"view_channel": True},
        "modo": {"view_channel": True},
    },
    "modo": {
        "everyone": {"view_channel": False},
        "createur": {"view_channel": False},
        "modo": {"view_channel": True},
        "bots": {"view_channel": True, "send_messages": True},
    },
}

# Catégories et salons, dans l'ordre d'affichage.
# "type" : "texte" (par défaut), "vocal", "forum" ou "scene".
# "annonce": True = salon d'annonces que d'autres serveurs peuvent suivre.
# Forum : "tags" = étiquettes ("emoji nom"), "vue": "galerie", "reaction" = emoji de vote.
# "sujet" = description, "lent" = mode lent (s), "limite" = places en vocal,
# "cle" = pour y faire référence (messages, questionnaire...), "ancien" = ancien nom.
CATEGORIES = [
    {"nom": "📌 WELCOME", "ancien": "📌 BIENVENUE", "salons": [
        {"cle": "bienvenue", "nom": "👋・welcome", "ancien": "👋・bienvenue",
         "acces": "lecture_seule", "sujet": "Welcome to the server!"},
        {"cle": "arrivees", "nom": "🛬・arrivals", "ancien": "🛬・arrivées",
         "acces": "lecture_seule", "sujet": "New members land here."},
        {"cle": "regles", "nom": "📜・rules", "ancien": "📜・règles",
         "acces": "lecture_seule", "sujet": "Read before joining the conversation."},
        {"cle": "staff", "nom": "📩・contact-staff", "ancien": "📩・contacter-le-staff",
         "acces": "lecture_seule", "sujet": "Open a private ticket with the team."},
    ]},
    {"nom": "🗺️ OUR MAPS", "ancien": "🗺️ NOS MAPS", "salons": [
        {"cle": "annonces", "nom": "📢・announcements", "ancien": "📢・annonces",
         "acces": "lecture_seule", "annonce": True, "sujet": "Map releases and big news."},
        {"cle": "maps", "nom": "🗺️・our-maps", "ancien": "🗺️・nos-maps", "type": "forum",
         "acces": "lecture_seule", "vue": "galerie",
         "sujet": "One page per map: island code, overview, and your feedback in the comments.",
         "tags": ["🆕 New", "🔄 Updated", "💰 Tycoon", "🎯 PvP", "🎉 Party", "🧗 Parkour"]},
        {"cle": "majs", "nom": "🔄・updates", "ancien": "🔄・mises-à-jour",
         "acces": "lecture_seule", "annonce": True, "sujet": "Patch notes and changes to our maps."},
        {"cle": "news", "nom": "📰・news", "acces": "lecture_seule",
         "sujet": "Our latest posts on X: follow @FantastikFTN!"},
        {"cle": "suggestions", "nom": "💡・suggestions", "type": "forum", "reaction": "👍",
         "sujet": "Got an idea for a map or an improvement? Create a post and vote with 👍.",
         "tags": ["🆕 New map", "🔧 Improvement", "🎉 Event", "✅ Accepted", "❌ Declined"]},
        {"cle": "bugs", "nom": "🐛・bug-reports", "ancien": "🐛・bugs", "type": "forum",
         "sujet": "One post per bug: map name, what happened, and a screenshot if you can.",
         "tags": ["🔴 Critical", "🟠 Major", "🟢 Minor", "🔍 Investigating", "✅ Fixed"]},
        {"nom": "🏆・high-scores", "ancien": "🏆・records",
         "sujet": "Show off your best scores and times on our maps."},
    ]},
    {"nom": "💬 COMMUNITY", "ancien": "💬 COMMUNAUTÉ", "salons": [
        {"cle": "general", "nom": "💬・general", "ancien": "💬・général",
         "sujet": "Chat about anything, in English, and be kind."},
        {"cle": "lfg", "nom": "🎮・looking-for-group", "ancien": "🎮・cherche-équipe",
         "sujet": "Find players to team up with."},
        {"nom": "📸・clips-and-screenshots", "ancien": "📸・clips-et-screens",
         "sujet": "Your best moments on our maps.", "lent": 30},
        {"nom": "🎥・videos-and-streams", "ancien": "🎥・vidéos-et-streams",
         "acces": "vitrine_contenu", "sujet": "Videos and streams from our content creators."},
        {"nom": "😂・memes"},
        {"cle": "niveaux", "nom": "📊・levels", "ancien": "📊・niveaux",
         "acces": "lecture_seule", "sujet": "Community level-ups."},
        {"cle": "commandes", "nom": "🤖・bot-commands", "ancien": "🤖・commandes-bot",
         "sujet": "Bot commands go here."},
    ]},
    {"nom": "🎉 EVENTS", "salons": [
        {"nom": "📅・events", "acces": "lecture_seule", "sujet": "Upcoming events and sessions."},
        {"nom": "🏅・tournaments", "ancien": "🏅・tournois",
         "sujet": "Tournament sign-ups and results."},
        {"nom": "🎁・giveaways", "acces": "lecture_seule", "sujet": "Prizes up for grabs."},
        {"nom": "🎤 Stage", "ancien": "🎤 Scène", "type": "scene"},
    ]},
    {"nom": "🔊 VOICE", "ancien": "🔊 VOCAUX", "salons": [
        {"nom": "🔊 General", "ancien": "🔊 Général", "type": "vocal"},
        {"nom": "🎮 Squad 1", "ancien": "🎮 Partie 1", "type": "vocal", "limite": 4},
        {"nom": "🎮 Squad 2", "ancien": "🎮 Partie 2", "type": "vocal", "limite": 4},
        {"nom": "🎥 Stream", "type": "vocal"},
        {"cle": "afk", "nom": "💤 AFK", "type": "vocal"},
    ]},
    {"nom": "🧪 BETA TESTING", "ancien": "🧪 BÊTA-TEST", "acces": "beta", "salons": [
        {"nom": "🧪・current-tests", "ancien": "🧪・tests-en-cours", "acces": "lecture_seule",
         "sujet": "Maps in testing and what to check."},
        {"nom": "📝・tester-feedback", "ancien": "📝・retours-testeurs",
         "sujet": "Your feedback on test builds."},
        {"nom": "🔊 Testing", "ancien": "🔊 Test", "type": "vocal"},
    ]},
    {"nom": "🛠️ TEAM", "ancien": "🛠️ ÉQUIPE", "acces": "equipe", "salons": [
        {"cle": "ajout_maps", "nom": "➕・add-a-map",
         "sujet": "Paste an island code (e.g. 1234-5678-9012), with a description and "
                  "screenshots if you like: within ~10 minutes the bot creates or refreshes "
                  "its page in #our-maps."},
        {"nom": "📋・tasks", "ancien": "📋・tâches", "sujet": "What's left to do."},
        {"nom": "💻・verse", "sujet": "Verse code, devices and UEFN logic."},
        {"nom": "🎨・design", "sujet": "Ideas, sketches and assets."},
        {"nom": "🔒・moderation", "ancien": "🔒・modération", "acces": "modo"},
        {"cle": "logs", "nom": "📜・logs", "acces": "modo"},
        {"nom": "🔊 Meeting", "ancien": "🔊 Réunion", "type": "vocal"},
    ]},
    # Les tickets ouverts avec Ticket Tool arrivent dans cette catégorie
    {"nom": "🎫 TICKETS", "acces": "modo", "salons": []},
]

# Salons d'une ancienne version du script, supprimés s'ils ne contiennent rien
# d'autre que des messages du bot.
ANCIENS_SALONS = ["⭐・avis"]

# Questionnaire d'arrivée (Onboarding), posé à chaque nouveau membre.
# Chaque réponse donne des "roles" (par cle) et/ou affiche des "salons" (par cle).
QUESTIONNAIRE = [
    {"titre": "What brings you here?", "obligatoire": True, "reponses": [
        {"titre": "Play our maps", "emoji": "🎮",
         "description": "Island codes, map pages and players", "salons": ["maps", "lfg"]},
        {"titre": "Test maps before release", "emoji": "🧪",
         "description": "Access to the beta testing channels", "roles": ["testeur"]},
        {"titre": "I make videos or streams", "emoji": "🎥",
         "description": "Share your content in #videos-and-streams", "roles": ["contenu"]},
    ]},
    {"titre": "What do you want to be notified about?", "obligatoire": False, "reponses": [
        {"titre": "New maps and updates", "emoji": "🆕", "roles": ["notif_maps"]},
        {"titre": "Events, tournaments and giveaways", "emoji": "🏆", "roles": ["notif_events"]},
    ]},
    {"titre": "Where do you play?", "obligatoire": False, "reponses": [
        {"titre": "PC", "emoji": "💻", "roles": ["pc"]},
        {"titre": "PlayStation", "emoji": "🎮", "roles": ["playstation"]},
        {"titre": "Xbox", "emoji": "🟢", "roles": ["xbox"]},
        {"titre": "Switch", "emoji": "🔴", "roles": ["switch"]},
        {"titre": "Mobile", "emoji": "📱", "roles": ["mobile"]},
    ]},
]

# Tes maps : une fiche par map dans le forum #our-maps (le titre sert à retrouver la fiche).
# "page" = page fortnite.com (bouton "Play now"), "image" = visuel principal,
# "captures" = jusqu'à 3 images affichées en galerie, "champs" = infos en plus,
# "tags" = tags du forum (sans l'emoji).
CDN = "https://cdn-0001.qstv.on.epicgames.com"
MAPS = [
    {"nom": "🍔 Eat Everything In A Grocery Store", "code": "3102-0284-4546",
     "page": "https://www.fortnite.com/@fantastik/3102-0284-4546",
     "description": "🍎 **EAT EVERYTHING IN THE GROCERY!** 🛒\n\n"
                    "🍔 **EAT IT ALL!** Devour food, shelves, and giant items to earn calories!\n"
                    "💪 **UPGRADE!** Spend calories to eat faster, grow stronger, and unlock "
                    "powerful boosts!\n"
                    "👥 **PLAY WITH FRIENDS!** Team up and clear the entire store!\n"
                    "📖 **COLLECT!** Discover tons of different foods and hidden secrets!\n"
                    "💰 **COMPLETE THE CHALLENGE!** Eat everything and become the ultimate "
                    "eating champion!\n\n"
                    "🏆 *Can you eat the entire grocery store?*",
     "image": f"{CDN}/AaZboBLfbuYwnyXWJX/image/landscape_comp.jpeg",
     "captures": [f"{CDN}/lZsXMyCYhQFYOXrkNF/image/screenshot_{i}.jpeg" for i in range(3)],
     "champs": [("🎮 Genre", "Tycoon · Simulator · Casual")],
     "tags": ["Tycoon"]},
    {"nom": "💨 FART TOGETHER", "code": "2952-6596-4953",
     "page": "https://www.fortnite.com/@fantastik/2952-6596-4953",
     "description": "🛶 **4 TEAMS OF 4** - 16 players, zero brain cells.\n"
                    "🍑 **FART TO MOVE** - Your back is your engine!\n"
                    "🤜🤛 **WORK TOGETHER** - Or blame your friends.\n"
                    "💥 **DIE & RESPAWN** - Blame the guy who farted.\n"
                    "🏆 **RACE TO THE FINISH** - If you survive your teammates.\n\n"
                    "One raft. Four idiots. Infinite chaos. 🤪\n\n"
                    "🚨 *WARNING: FRIENDSHIPS NOT INCLUDED.*",
     "image": f"{CDN}/zTSjWadhrDUlhQcECW/image/landscape_comp.jpeg",
     "captures": [f"{CDN}/zTSjWadhrDUlhQcECW/image/screenshot_{i}.jpeg" for i in range(3)],
     "champs": [("🎮 Genre", "Deathrun · Parkour · Party"), ("👥 Players", "16 (4 teams of 4)")],
     "tags": ["Parkour", "Party"]},
]
BOUTON_JOUER = "Play now"

# Messages postés (puis mis à jour à chaque lancement) par le bot.
# {regles}, {maps}... deviennent des liens vers les salons ayant cette "cle".
BIENVENUE = {
    "titre": "👋 Welcome to {serveur}!",
    "description": "**The HQ of our Fortnite maps.** All our creations, their island codes, "
                   "sneak peeks of what's coming and community events.",
    "champs": [
        ("🗺️ Our maps", "Codes and map pages in {maps}"),
        ("📢 News", "Releases in {annonces}\nPatch notes in {majs}\nOur X posts in {news}"),
        ("💡 Your feedback", "Ideas in {suggestions}\nBugs in {bugs}"),
        ("🎭 Your roles", "Change them in **Channels & Roles**, at the top of the channel list"),
        ("📜 Rules", "Read them in {regles}"),
        ("📩 Staff", "Need help? Use {staff}"),
    ],
}

REGLES = {
    "titre": "📜 Server Rules",
    "pied": "By staying on this server, you agree to these rules.",
    "liste": [
        "Be respectful: no insults, harassment, racism or discrimination.",
        "No spam, flooding or self-promotion without permission (servers, channels, links).",
        "No NSFW, shocking or illegal content.",
        "No cheating. Found a glitch on a map? Report it in {bugs} instead of sharing it.",
        "Use the right channels, and please speak English in public channels so everyone "
        "can join in.",
        "No offensive usernames or profile pictures.",
        "Respect the moderators' decisions. Any issue? Open a ticket in {staff}.",
        "Follow [Discord's Terms of Service](https://discord.com/terms) "
        "and Epic Games' rules.",
    ],
}

ARRIVEES = {
    "titre": "🛬 Arrivals",
    "texte": "Every new member shows up here. Go say hi in {general}!",
}

STAFF = {
    "titre": "📩 Need the team?",
    "texte": "Reports, partnerships, questions about a map...\n"
             "Click the button right below to open a **private ticket** with the staff.",
}

NIVEAUX = {
    "titre": "📊 Levels",
    "intro": "Chat, join events, post your clips: you earn XP and unlock roles.",
    "ligne": "**Level {niveau}** → {role}",
    "fin": "`/rank` to see your level · `/leaderboard` for the ranking",
}

GUIDE_MAPS = {
    "titre": "🎮 How to play our maps",
    "ancien": "🎮 Comment jouer à nos maps",
    "texte": "**1.** Launch Fortnite and open the **Discover** tab.\n"
             "**2.** Click the search icon and type the **island code** (e.g. `1234-5678-9012`).\n"
             "**3.** Start the game, then come back and leave your feedback on the map's page!\n\n"
             "🔔 Grab the **Map Alerts** role in *Channels & Roles* so you never miss a release.",
}

COMMANDES = {
    "titre": "🤖 Useful commands",
    "champs": [
        ("📊 Levels", "`/rank` your level\n`/leaderboard` the ranking"),
        ("🎁 Giveaways (staff)", "`/gcreate` to start a giveaway"),
        ("📩 Tickets", "The button in {staff}"),
    ],
}

CODE_ILE = "🏝️ Island code"  # nom du champ dans les fiches de maps

# Règles AutoMod : (nom, ancien nom, type, réglages, message affiché quand c'est bloqué)
AUTOMOD = [
    ("Anti-spam", None, "spam", {}, None),
    ("Mass mentions", "Mentions en masse", "mention_spam",
     {"mention_limit": 5, "mention_raid_protection": True}, None),
    ("Banned language", "Langage interdit", "keyword_preset",
     {"presets": {"slurs": True, "sexual_content": True}},
     "Message blocked: this language isn't allowed here."),
    ("Discord invites", "Invitations Discord", "keyword",
     {"regex_patterns": [r"discord(app)?\.(gg|com/invite)/"]},
     "Invites to other servers aren't allowed."),
]

# Catégories et salons que Discord crée sur un serveur neuf (pour --supprimer-defauts)
CATEGORIES_PAR_DEFAUT = {"salons textuels", "salons vocaux", "text channels", "voice channels"}
SALONS_PAR_DEFAUT = {"général", "general"}

# =====================================================================
#  SCRIPT — pas besoin de toucher la suite
# =====================================================================

TYPES = {"texte": "text_channels", "vocal": "voice_channels", "forum": "forums",
         "scene": "stage_channels"}


def log(symbole, texte):
    print(f"  {symbole} {texte}")


def normaliser(nom):
    """Discord met les noms de salons textuels en minuscules avec des tirets."""
    return nom.replace("️", "").strip().lower().replace(" ", "-")


def trouver(collection, nom):
    cible = normaliser(nom)
    return next((x for x in collection if normaliser(x.name) == cible), None)


def retrouver(collection, element):
    """Cherche par le nom actuel, puis par l'ancien nom s'il y en a un."""
    trouve = trouver(collection, element["nom"])
    if trouve is None and "ancien" in element:
        trouve = trouver(collection, element["ancien"])
    return trouve


def nouveau_nom(objet, nom):
    """Le nom à envoyer à Discord, seulement s'il change (les renommages sont limités)."""
    return {} if normaliser(objet.name) == normaliser(nom) else {"name": nom}


def profils(cat, salon=None):
    noms = [cat["acces"]] if "acces" in cat else []
    if salon and "acces" in salon:
        noms.append(salon["acces"])
    return noms


def verifier_config():
    """Repère les fautes de frappe dans la configuration avant de toucher au serveur."""
    cles_roles = {r["cle"] for r in ROLES}
    for r in ROLES:
        discord.Permissions(**r.get("perms", {}))
    for nom, profil in ACCES.items():
        for cible, perms in profil.items():
            if cible not in ("everyone", "bots") and cible not in cles_roles:
                sys.exit(f"Profil '{nom}' : rôle inconnu '{cible}'")
            discord.PermissionOverwrite(**perms)
    for cat in CATEGORIES:
        for salon in [None, *cat["salons"]]:
            for profil in profils(cat, salon):
                if profil not in ACCES:
                    sys.exit(f"{cat['nom']} : profil d'accès inconnu '{profil}'")
            if salon and salon.get("type", "texte") not in TYPES:
                sys.exit(f"{salon['nom']} : type inconnu '{salon['type']}'")
            if salon and any(" " not in tag for tag in salon.get("tags", [])):
                sys.exit(f"{salon['nom']} : les tags s'écrivent \"emoji nom\"")
    cles_salons = {s.get("cle", s["nom"]) for cat in CATEGORIES for s in cat["salons"]}
    for question in QUESTIONNAIRE:
        for reponse in question["reponses"]:
            inconnus = (set(reponse.get("roles", [])) - cles_roles) | \
                       (set(reponse.get("salons", [])) - cles_salons)
            if inconnus:
                sys.exit(f"Questionnaire, '{reponse['titre']}' : cle inconnue {inconnus}")
            if not reponse.get("roles") and not reponse.get("salons"):
                sys.exit(f"Questionnaire, '{reponse['titre']}' : il faut au moins un rôle ou un salon")
    for _, _, type_, reglages, _ in AUTOMOD:
        reglages = dict(reglages)
        if "presets" in reglages:
            reglages["presets"] = discord.AutoModPresets(**reglages["presets"])
        discord.AutoModTrigger(type=discord.AutoModRuleTriggerType[type_], **reglages)


def overwrites(noms_profils, roles, everyone):
    resultat = {}
    for nom in noms_profils:
        for cible, perms in ACCES[nom].items():
            if cible == "everyone":
                objets = [everyone]
            elif cible == "bots":
                objets = roles["bots"]
            else:
                objets = [roles[cible]]
            for obj in objets:
                resultat.setdefault(obj, discord.PermissionOverwrite()).update(**perms)
    return resultat


async def preparer_roles(guild):
    print("Rôles")
    roles = {}
    for r in ROLES:
        options = dict(
            permissions=discord.Permissions(**r.get("perms", {})),
            colour=discord.Colour(r.get("couleur", 0)),
            hoist=r.get("separe", False),
            mentionable=r.get("mentionnable", False),
        )
        role = retrouver(guild.roles, r)
        if role:
            await role.edit(**nouveau_nom(role, r["nom"]), **options, reason=RAISON)
            log("~", r["nom"])
        else:
            role = await guild.create_role(name=r["nom"], **options, reason=RAISON)
            log("+", r["nom"])
        roles[r["cle"]] = role

    for nom in ANCIENS_ROLES:
        ancien = trouver(guild.roles, nom)
        if ancien:
            await ancien.delete(reason=RAISON)
            log("-", nom)

    # Rôles gérés par les autres bots (Arcane, Ticket Tool...), rangés sous les modos
    # pour qu'ils puissent donner les rôles de niveau, Tester, etc.
    roles["bots"] = [r for r in guild.roles if r.is_bot_managed() and r != guild.self_role]
    ordre = []
    for r in ROLES:
        ordre.append(roles[r["cle"]])
        if r["cle"] == "modo":
            ordre += roles["bots"]

    # Range les rôles dans cet ordre, juste sous le rôle de ce bot
    ids_bot = {r.id for r in guild.me.roles}
    haut = max(r.position for r in await guild.fetch_roles() if r.id in ids_bot)
    positions = {role: max(haut - 1 - i, 1) for i, role in enumerate(ordre)}
    try:
        await guild.edit_role_positions(positions, reason=RAISON)
    except discord.HTTPException:
        log("!", "Impossible de ranger les rôles : place le rôle du bot tout en haut, puis relance.")

    try:
        proprio = await guild.fetch_member(guild.owner_id)
        if roles["fondateur"] not in proprio.roles:
            await proprio.add_roles(roles["fondateur"], reason=RAISON)
            log("+", f"{roles['fondateur'].name} donné à {proprio.display_name}")
    except discord.HTTPException:
        log("!", "Impossible de donner le rôle Founder au propriétaire.")
    return roles


async def seulement_le_bot(salon, guild):
    """Vrai si le salon est vide ou ne contient que des messages de ce bot."""
    async for message in salon.history(limit=50):
        if message.author.id != guild.me.id:
            return False
    return True


async def liberer_nom(guild, element):
    """Retire un ancien salon textuel qui porte le nom d'un salon à recréer sous un autre type."""
    ancien = retrouver(guild.text_channels, element)
    if ancien is None:
        return
    if await seulement_le_bot(ancien, guild):
        await ancien.delete(reason=RAISON)
        log("-", f"{ancien.name} (ancienne version textuelle)")
    else:
        await ancien.edit(name=f"{ancien.name}-archive", reason=RAISON)
        log("!", f"{ancien.name} contient des messages : renommé en {ancien.name}-archive")


async def preparer_salons(guild, roles, communaute):
    """Forums, salons d'annonces et scène n'existent qu'en mode communauté."""
    everyone = guild.default_role
    salons = {}
    rangement = []
    for cat in CATEGORIES:
        print(cat["nom"])
        ow_cat = overwrites(profils(cat), roles, everyone)
        categorie = retrouver(guild.categories, cat)
        if categorie:
            await categorie.edit(**nouveau_nom(categorie, cat["nom"]), overwrites=ow_cat,
                                 reason=RAISON)
        else:
            categorie = await guild.create_category(cat["nom"], overwrites=ow_cat, reason=RAISON)

        contenu = []
        for s in cat["salons"]:
            type_ = s.get("type", "texte")
            if type_ in ("forum", "scene") and not communaute:
                continue
            salon = retrouver(getattr(guild, TYPES[type_]), s)
            if salon is None and type_ != "texte":
                await liberer_nom(guild, s)

            options = {"overwrites": overwrites(profils(cat, s), roles, everyone)}
            if type_ in ("texte", "forum"):
                options["slowmode_delay"] = s.get("lent", 0)
                # Comme le nom, le sujet n'est envoyé que s'il change
                if salon is None or salon.topic != s.get("sujet"):
                    options["topic"] = s.get("sujet")
            if type_ == "vocal":
                options["user_limit"] = s.get("limite", 0)
            if type_ == "forum":
                # Réutilise les tags existants pour ne pas les retirer des posts déjà tagués
                existants = {t.name: t for t in salon.available_tags} if salon else {}
                options["available_tags"] = [
                    existants.get(nom) or discord.ForumTag(name=nom, emoji=emoji)
                    for emoji, nom in (tag.split(" ", 1) for tag in s.get("tags", []))]
                options["default_layout"] = (discord.ForumLayoutType.gallery_view
                                             if s.get("vue") == "galerie"
                                             else discord.ForumLayoutType.list_view)
                if "reaction" in s:
                    options["default_reaction_emoji"] = s["reaction"]
            annonce = communaute and s.get("annonce", False)

            if salon:
                if type_ == "texte" and annonce and not salon.is_news():
                    options["type"] = discord.ChannelType.news
                await salon.edit(**nouveau_nom(salon, s["nom"]), category=categorie, **options,
                                 reason=RAISON)
                log("~", s["nom"])
            else:
                if type_ == "texte":
                    salon = await guild.create_text_channel(s["nom"], category=categorie,
                                                            news=annonce, **options, reason=RAISON)
                elif type_ == "vocal":
                    salon = await guild.create_voice_channel(s["nom"], category=categorie,
                                                             **options, reason=RAISON)
                elif type_ == "forum":
                    salon = await guild.create_forum(s["nom"], category=categorie,
                                                     **options, reason=RAISON)
                else:
                    salon = await guild.create_stage_channel(s["nom"], category=categorie,
                                                             **options, reason=RAISON)
                log("+", s["nom"])
            salons[s.get("cle", s["nom"])] = salon
            contenu.append(salon)
        rangement.append((categorie, contenu))

    await ranger(guild, rangement)
    return salons


async def ranger(guild, rangement):
    """Remet catégories et salons dans l'ordre de la configuration, en un seul appel."""
    nos_categories = [categorie for categorie, _ in rangement]
    autres = [c for c in guild.categories if c not in nos_categories]
    base = max((c.position for c in autres), default=-1) + 1
    donnees = [{"id": c.id, "position": base + i} for i, c in enumerate(nos_categories)]
    for _, contenu in rangement:
        vocaux = [c for c in contenu if isinstance(c, (discord.VoiceChannel, discord.StageChannel))]
        textes = [c for c in contenu if c not in vocaux]
        # Les salons sont déjà dans la bonne catégorie : Discord refuse de changer
        # le parent de plusieurs salons dans le même appel.
        for groupe in (textes, vocaux):
            donnees += [{"id": c.id, "position": i} for i, c in enumerate(groupe)]
    # discord.py n'expose pas cet appel groupé, d'où le passage par son client HTTP
    await guild._state.http.bulk_channel_update(guild.id, donnees, reason=RAISON)


async def supprimer_anciens(guild):
    for nom in ANCIENS_SALONS:
        ancien = trouver(guild.text_channels, nom)
        if ancien is None:
            continue
        if await seulement_le_bot(ancien, guild):
            await ancien.delete(reason=RAISON)
            log("-", nom)
        else:
            log("!", f"{nom} contient des messages : je le laisse, supprime-le à la main si besoin.")


async def regler_serveur(guild, salons):
    print("Réglages du serveur")
    flags = guild.system_channel_flags
    flags.join_notifications = True
    flags.premium_subscriptions = True
    flags.join_notification_replies = False  # #arrivals est en lecture seule
    flags.guild_reminder_notifications = False
    await guild.edit(
        afk_channel=salons.get("afk"),
        afk_timeout=300,
        system_channel=salons.get("arrivees"),
        system_channel_flags=flags,
        reason=RAISON,
    )
    log("~", "Arrivées et boosts annoncés dans #arrivals, salon AFK après 5 min")

    # Évite que n'importe qui puisse pinger @everyone / @here
    perms = guild.default_role.permissions
    perms.update(mention_everyone=False)
    await guild.default_role.edit(permissions=perms, reason=RAISON)
    log("~", "@everyone ne peut plus mentionner tout le monde")


async def activer_communaute(guild, salons):
    """Le mode communauté est obligatoire pour le questionnaire, les forums et les annonces."""
    print("Mode communauté")
    try:
        await guild.edit(
            community=True,
            rules_channel=salons["regles"],
            public_updates_channel=salons["logs"],
            description=DESCRIPTION,
            preferred_locale=LANGUE,
            verification_level=max(guild.verification_level, discord.VerificationLevel.low),
            explicit_content_filter=discord.ContentFilter.all_members,
            default_notifications=discord.NotificationLevel.only_mentions,
            reason=RAISON,
        )
    except discord.HTTPException as erreur:
        log("!", f"Impossible d'activer le mode communauté : {erreur.text}")
        return False
    log("~", f"Activé, langue {LANGUE.value} : e-mail vérifié, filtre d'images, notifs sur @mention")
    return True


async def configurer_onboarding(guild, roles, salons):
    print("Questionnaire d'arrivée")
    questions = []
    for question in QUESTIONNAIRE:
        reponses = []
        for r in question["reponses"]:
            options = {"title": r["titre"], "description": r.get("description"),
                       "roles": [roles[c] for c in r.get("roles", [])],
                       "channels": [salons[c] for c in r.get("salons", [])]}
            if "emoji" in r:
                options["emoji"] = r["emoji"]
            reponses.append(discord.OnboardingPromptOption(**options))
        questions.append(discord.OnboardingPrompt(
            type=discord.OnboardingPromptType.multiple_choice,
            title=question["titre"],
            options=reponses,
            single_select=False,
            required=question["obligatoire"],
            in_onboarding=True,
        ))

    # Salons affichés d'office : tous ceux des catégories publiques
    publics = [salons[s.get("cle", s["nom"])]
               for cat in CATEGORIES if "acces" not in cat for s in cat["salons"]]
    try:
        await guild.edit_onboarding(prompts=questions, default_channels=publics, enabled=True,
                                    mode=discord.OnboardingMode.default, reason=RAISON)
    except discord.HTTPException as erreur:
        log("!", f"Impossible de configurer le questionnaire : {erreur.text}")
        return
    for question in QUESTIONNAIRE:
        log("~", question["titre"])


async def configurer_automod(guild, roles, salons):
    """Règles AutoMod de Discord : bloquent le message et préviennent les modos dans #logs."""
    print("AutoMod")
    T = discord.AutoModRuleTriggerType
    alerte = [discord.AutoModRuleAction(channel_id=salons["logs"].id)] if "logs" in salons else []
    existantes = await guild.fetch_automod_rules()
    uniques = {T.spam, T.mention_spam, T.keyword_preset}  # Discord n'en autorise qu'une de chaque

    for nom, ancien, type_, reglages, message in AUTOMOD:
        reglages = dict(reglages)
        if "presets" in reglages:
            reglages["presets"] = discord.AutoModPresets(**reglages["presets"])
        declencheur = discord.AutoModTrigger(type=T[type_], **reglages)
        actions = [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message,
                                             custom_message=message)]
        if declencheur.type == T.mention_spam:
            actions.append(discord.AutoModRuleAction(duration=timedelta(minutes=10)))

        regle = next((r for r in existantes if r.name in (nom, ancien)), None)
        if regle is None and declencheur.type in uniques:
            regle = next((r for r in existantes if r.trigger.type == declencheur.type), None)
        if regle and regle.creator_id != guild.me.id:
            # Règle créée par Discord (mode communauté) : un bot ne peut pas la modifier
            log("~", f"{nom} : la règle « {regle.name} » de Discord est déjà active")
            continue
        options = dict(name=nom, event_type=discord.AutoModRuleEventType.message_send,
                       trigger=declencheur, actions=actions + alerte, enabled=True,
                       exempt_roles=[roles["modo"], roles["createur"]], reason=RAISON)
        try:
            if regle:
                await regle.edit(**options)
                log("~", nom)
            else:
                await guild.create_automod_rule(**options)
                log("+", nom)
        except discord.HTTPException as erreur:
            log("!", f"{nom} : {erreur.text}")


async def supprimer_defauts(guild):
    print("Salons par défaut de Discord")
    for categorie in list(guild.categories):
        if categorie.name.lower() not in CATEGORIES_PAR_DEFAUT:
            continue
        for salon in list(categorie.channels):
            if salon.name.lower() in SALONS_PAR_DEFAUT:
                await salon.delete(reason=RAISON)
                log("-", f"{categorie.name} / {salon.name}")
        if not categorie.channels:
            await categorie.delete(reason=RAISON)
            log("-", categorie.name)


async def donner_fondateur(guild, roles):
    print("Fondateurs")
    role = roles["fondateur"]
    async for membre in guild.fetch_members(limit=None):
        if membre.bot or role in membre.roles:
            continue
        await membre.add_roles(role, reason=RAISON)
        log("+", f"{role.name} donné à {membre.display_name}")


class _Mentions(dict):
    def __missing__(self, cle):
        return f"#{cle}"


async def publier(salon, moi, **contenu):
    """Poste le message du bot, ou met à jour celui qu'il a déjà posté dans ce salon."""
    async for message in salon.history(limit=20, oldest_first=True):
        if message.author.id == moi.id:
            await message.edit(**contenu)
            return "~"
    await salon.send(**contenu)
    return "+"


async def publier_post(forum, moi, titre, ancien=None, epingle=False, tags=(), **contenu):
    """Crée un post de forum, ou met à jour celui du même titre (ou de l'ancien titre)."""
    titres = (titre, ancien)
    fil = next((t for t in forum.threads if t.name in titres), None)
    if fil is None:
        async for archive in forum.archived_threads(limit=100):
            if archive.name in titres:
                fil = archive
                break
    appliques = [t for t in forum.available_tags if t.name in tags]
    if fil:
        message = await fil.fetch_message(fil.id)  # le premier message a l'ID du post
        if message.author.id == moi.id:
            await message.edit(**contenu)
        if fil.name != titre:
            await fil.edit(name=titre)
        etat = "~"
    else:
        fil, _ = await forum.create_thread(name=titre, applied_tags=appliques, **contenu,
                                           reason=RAISON)
        etat = "+"
    if epingle and not fil.flags.pinned:
        await fil.edit(pinned=True)
    return etat


async def poster_messages(guild, roles, salons):
    print("Messages")
    moi = guild.me
    mentions = _Mentions({cle: s.mention for cle, s in salons.items()}, serveur=guild.name)
    icone = guild.icon.url if guild.icon else None

    def carte(titre, description="", champs=()):
        embed = discord.Embed(title=titre.format_map(mentions),
                              description=description.format_map(mentions), colour=COULEUR)
        for nom, valeur in champs:
            embed.add_field(name=nom, value=valeur.format_map(mentions))
        if icone:
            embed.set_thumbnail(url=icone)
        embed.set_footer(text=f"{guild.name} • {PIED}", icon_url=icone)
        return embed

    regles = carte(REGLES["titre"],
                   "\n\n".join(f"**{i}.** {r}" for i, r in enumerate(REGLES["liste"], 1)))
    regles.set_footer(text=REGLES["pied"], icon_url=icone)
    paliers = "\n".join(NIVEAUX["ligne"].format(niveau=r["niveau"], role=roles[r["cle"]].mention)
                        for r in ROLES if "niveau" in r)

    messages = {
        "bienvenue": carte(BIENVENUE["titre"], BIENVENUE["description"], BIENVENUE["champs"]),
        "regles": regles,
        "arrivees": carte(ARRIVEES["titre"], ARRIVEES["texte"]),
        "staff": carte(STAFF["titre"], STAFF["texte"]),
        "niveaux": carte(NIVEAUX["titre"],
                         f"{NIVEAUX['intro']}\n\n{paliers}\n\n{NIVEAUX['fin']}"),
        "commandes": carte(COMMANDES["titre"], champs=COMMANDES["champs"]),
    }
    for cle, embed in messages.items():
        if cle in salons:
            log(await publier(salons[cle], moi, embed=embed), salons[cle].name)

    forum = salons.get("maps")
    if isinstance(forum, discord.ForumChannel):
        guide = carte(GUIDE_MAPS["titre"], GUIDE_MAPS["texte"])
        log(await publier_post(forum, moi, GUIDE_MAPS["titre"], ancien=GUIDE_MAPS.get("ancien"),
                               epingle=True, embed=guide),
            f"{forum.name} / {GUIDE_MAPS['titre']}")
        for m in MAPS:
            fiche = carte(m["nom"], m.get("description", ""),
                          [(CODE_ILE, f"`{m['code']}`"), *m.get("champs", [])])
            if m.get("image"):
                fiche.set_image(url=m["image"])
            contenu = {"embeds": [fiche]}
            if m.get("page"):
                fiche.url = m["page"]
                # Des embeds qui partagent la même URL s'affichent en galerie d'images
                contenu["embeds"] += [discord.Embed(url=m["page"]).set_image(url=capture)
                                      for capture in m.get("captures", [])[:3]]
                vue = discord.ui.View()
                vue.add_item(discord.ui.Button(label=BOUTON_JOUER, emoji="▶️", url=m["page"]))
                contenu["view"] = vue
            log(await publier_post(forum, moi, m["nom"], tags=m.get("tags", []), **contenu),
                f"{forum.name} / {m['nom']}")


async def construire(guild, avec_suppression, avec_fondateurs):
    print(f"Serveur : {guild.name}\n")
    roles = await preparer_roles(guild)
    communaute = "COMMUNITY" in guild.features
    salons = await preparer_salons(guild, roles, communaute)
    await regler_serveur(guild, salons)
    if await activer_communaute(guild, salons):
        if not communaute:  # 2e passage pour créer forums, annonces et scène
            salons = await preparer_salons(guild, roles, True)
        await configurer_onboarding(guild, roles, salons)
    await configurer_automod(guild, roles, salons)
    await supprimer_anciens(guild)
    if avec_suppression:
        await supprimer_defauts(guild)
    await poster_messages(guild, roles, salons)
    if avec_fondateurs:
        await donner_fondateur(guild, roles)

    if "bienvenue" in salons:
        invitation = await salons["bienvenue"].create_invite(max_age=0, max_uses=0, unique=False,
                                                              reason=RAISON)
        print(f"\nTerminé ! Lien d'invitation permanent : {invitation.url}")


def afficher_apercu():
    print("RÔLES (du plus haut au plus bas)")
    for r in ROLES:
        if r.get("perms", {}).get("administrator"):
            details = "  — admin"
        elif "niveau" in r:
            details = f"  — niveau {r['niveau']}"
        else:
            details = ""
        print(f"  {r['nom']}{details}")
        if r["cle"] == "modo":
            print("  (rôles des bots)")
    for cat in CATEGORIES:
        print(f"\n{cat['nom']}" + (f"   [{cat['acces']}]" if "acces" in cat else ""))
        for s in cat["salons"]:
            type_ = s.get("type", "texte")
            if type_ in ("vocal", "scene"):
                details = "scène" if type_ == "scene" else "vocal"
                details += f", {s['limite']} places" if s.get("limite") else ""
                print(f"    {s['nom']}   ({details})")
            else:
                details = [s["acces"]] if "acces" in s else []
                details += ["forum"] if type_ == "forum" else []
                details += ["annonces"] if s.get("annonce") else []
                print(f"  # {s['nom']}" + (f"   [{', '.join(details)}]" if details else ""))
    print("\nQUESTIONNAIRE D'ARRIVÉE")
    for question in QUESTIONNAIRE:
        print(f"  {question['titre']}" + ("  (obligatoire)" if question["obligatoire"] else ""))
        for r in question["reponses"]:
            print(f"    {r.get('emoji', '•')} {r['titre']}  → {', '.join(r.get('roles', [])) or 'salons'}")


def lire_env(chemin):
    valeurs = {}
    if chemin.exists():
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, valeur = ligne.split("=", 1)
                valeurs[cle.strip()] = valeur.strip().strip("\"'")
    return valeurs


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    verifier_config()
    if "--apercu" in sys.argv:
        afficher_apercu()
        return

    env = lire_env(Path(__file__).with_name(".env"))
    token = os.environ.get("DISCORD_TOKEN") or env.get("DISCORD_TOKEN")
    guild_id = os.environ.get("GUILD_ID") or env.get("GUILD_ID", "")
    if not token or not guild_id.isdigit():
        sys.exit("Il manque DISCORD_TOKEN ou GUILD_ID dans le fichier .env (voir .env.example).")

    avec_fondateurs = "--fondateurs" in sys.argv
    intents = discord.Intents.default()
    intents.members = avec_fondateurs  # lister les membres demande cet intent privilégié
    client = discord.Client(intents=intents)
    etat = {"lance": False, "ok": False}

    @client.event
    async def on_ready():
        if etat["lance"]:  # on_ready peut se redéclencher après une reconnexion
            return
        etat["lance"] = True
        try:
            guild = client.get_guild(int(guild_id))
            if guild is None:
                print("Le bot n'est pas sur ce serveur : invite-le d'abord, et vérifie GUILD_ID.")
                return
            await construire(guild, "--supprimer-defauts" in sys.argv, avec_fondateurs)
            etat["ok"] = True
        except discord.Forbidden:
            print("\nPermission refusée : invite le bot avec la permission Administrateur "
                  "et place son rôle tout en haut.")
        except discord.HTTPException as erreur:
            print(f"\nErreur Discord : {erreur}")
        finally:
            await client.close()

    try:
        client.run(token, log_level=logging.WARNING)
    except discord.LoginFailure:
        sys.exit("Token invalide : régénère-le dans le portail développeur Discord.")
    except discord.PrivilegedIntentsRequired:
        sys.exit("Active « Server Members Intent » dans le portail développeur "
                 "(ton application > Bot), puis relance.")
    sys.exit(0 if etat["ok"] else 1)


if __name__ == "__main__":
    main()
