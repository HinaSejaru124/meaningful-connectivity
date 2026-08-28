"""
utils/net_utils.py

Utilitaires partagés pour construire des commandes curl sûres, quel
que soit le contenu des noms de fichiers (espaces, caractères
spéciaux...).

Deux problèmes distincts, deux fonctions :

1. encode_path_component() : encode un segment de chemin pour une URL
   HTTP (espace -> %20, etc.). Le serveur (http.server standard)
   décode automatiquement via urllib.parse.unquote côté réception,
   donc ceci est sans risque tant que le nom réel du fichier sur
   disque n'est pas modifié — seule sa représentation dans l'URL l'est.

2. shell_quote() : échappe une chaîne pour qu'elle soit insérée telle
   quelle comme UN SEUL argument dans une commande shell (via
   server.cmd()/client_host.cmd()), qu'elle contienne des espaces, des
   apostrophes, ou d'autres métacaractères shell.

Sans ces deux fonctions, un nom de fichier contenant un espace fait
que le shell scinde la commande en plusieurs arguments — la partie
après l'espace (potentiellement l'extension .pdf/.json/etc.) est
perdue ou mal interprétée par curl, provoquant un 404 silencieux.
"""

from urllib.parse import quote


def encode_path_component(name: str) -> str:
    """Encode un segment de chemin pour une URL (espace -> %20, etc.)."""
    return quote(name, safe="")


def shell_quote(value: str) -> str:
    """
    Échappe `value` pour une insertion sûre comme argument shell
    unique (guillemets simples POSIX, avec échappement des
    apostrophes internes éventuelles).
    """
    return "'" + value.replace("'", "'\"'\"'") + "'"