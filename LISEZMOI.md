# Fantastik — serveur Discord de nos maps Fortnite

`creer_serveur.py` monte et met à jour tout le serveur (en anglais, pour viser l'international) :
rôles, catégories, salons, forums, permissions, AutoMod, mode communauté, questionnaire
d'arrivée et messages du bot. Tu peux le relancer autant que tu veux : il renomme et met à jour
ce qui existe au lieu de créer des doublons.

## Lancer le script

Le fichier `.env` contient le token du bot « Fantastik Setup » et l'ID du serveur (ne le partage
jamais). Ensuite :

```bash
pip install -r requirements.txt
```

```bash
python creer_serveur.py --apercu
```

```bash
python creer_serveur.py
```

- `--apercu` affiche la structure sans rien toucher.
- `--fondateurs` donne 👑 Founder à **tous** les membres présents (à ne lancer qu'une fois ;
  « Server Members Intent » doit être activé dans l'onglet Bot du portail développeur).
- `--supprimer-defauts` retire les salons « général » créés par Discord (serveur neuf seulement).

## Ajouter une map

Colle le code de l'île (ex. `1234-5678-9012`) dans **#➕・add-a-map** (salon de l'équipe) : le bot
crée sa fiche dans #our-maps, avec titre, genres, tags du forum et bouton « Play now », puis répond
avec le lien.

- L'API d'Epic ne donne ni image ni description : écris la description dans le même message que
  le code et joins les images (1re = visuel principal, 3 suivantes = galerie).
- Recoller le code d'une map qui a déjà sa fiche, avec un texte ou des images, met la fiche à jour
  (tag 🔄 Updated). Les deux maps de `MAPS` sont réécrites par `creer_serveur.py` à chaque
  lancement : modifie-les plutôt dans le script.
- C'est **GitHub Actions** qui s'en charge, sans ton PC : toutes les 10 minutes environ
  (`.github/workflows/ajout-maps.yml`), il lance `python ajout_maps.py --une-fois`, qui traite
  les codes en attente puis s'arrête. Un code traité reçoit ✅ (ou ❌) et une réponse du bot.
- Pour ne pas attendre : onglet **Actions** du dépôt GitHub → **Add maps** → **Run workflow**.
- Le token du bot est dans les secrets du dépôt (Settings → Secrets and variables → Actions →
  `DISCORD_TOKEN`). Si tu fais Reset Token, remplace-le là aussi.
- Ne lance pas `python ajout_maps.py` sur ton PC en même temps : deux bots pourraient créer la
  même fiche en double.

## Personnaliser

Tout se règle en haut de `creer_serveur.py` :

- `MAPS` : tes maps (nom, code, description, image, tags) → une fiche par map dans le forum #our-maps ;
- `ROLES`, `CATEGORIES` : rôles et salons (mets l'ancien nom dans `"ancien"` pour renommer) ;
- `QUESTIONNAIRE` : les questions posées aux nouveaux membres et les rôles donnés ;
- `BIENVENUE`, `REGLES`, `GUIDE_MAPS`... : les textes des messages du bot ;
- `AUTOMOD` : les règles anti-spam, anti-invitations et langage.

## Les bots

| Bot | Rôle | Réglages |
|---|---|---|
| Fantastik Setup | Le nôtre : lance `creer_serveur.py` et `ajout_maps.py` (intents Server Members et Message Content activés) | Portail développeur Discord |
| Arcane | Niveaux et XP : Rookie (2), Builder (5), Sweaty (10), Pro (20), Legend (35), annonces et top 10 hebdo dans #levels | arcane.bot/dashboard |
| Carl-bot | Logs (messages supprimés/modifiés, arrivées, bans, rôles…) dans #logs | carl.gg/dashboard |
| Ticket Tool | Bouton « Create ticket » dans #contact-staff, tickets dans 🎫 TICKETS, transcriptions dans #logs | `/setup` dans Discord |
| GiveawayBot | `/gcreate` pour lancer un giveaway | — |
| ServerStats | Compteurs de membres en haut du serveur | `/counter list` dans Discord |

## Sécurité

Le bot « Fantastik Setup » est administrateur. Garde le `.env` pour toi ; si le token fuite,
fais **Reset Token** dans le portail développeur (onglet Bot) et remplace-le dans `.env`.
