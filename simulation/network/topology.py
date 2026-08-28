from mininet.net import Mininet
from mininet.link import TCLink

from pathlib import Path
from dataclasses import dataclass, field
import time


# ============================================================================
# Topologie Mininet
# ============================================================================

@dataclass
class TopologyBuilder:

    total_clients: int = 10
    server_host: str = "h_srv"
    switch_name: str = "s1"
    server_ip: str = "10.0.0.10"

    clients: list[str] = field(init=False)

    def __post_init__(self):
        self.clients = [
            f"h{i}"
            for i in range(1, self.total_clients + 1)
        ]

    # ------------------------------------------------------------------------
    # Construction de la topologie
    # ------------------------------------------------------------------------

    def build(self):

        self.net = Mininet(
            link=TCLink,
            controller=None,
            autoSetMacs=True
        )

        switch = self.net.addSwitch(self.switch_name)

        server = self.net.addHost(
            self.server_host,
            ip=f"{self.server_ip}/24"
        )

        self.net.addLink(server, switch)

        hosts = []

        for i, name in enumerate(self.clients, start=11):
            host = self.net.addHost(
                name,
                ip=f"10.0.0.{i}/24"
            )
            self.net.addLink(host, switch)
            hosts.append(host)

        self.net.start()

        # Autoriser le forwarding normal du switch OVS.
        switch.cmd(
            f"ovs-ofctl add-flow {self.switch_name} actions=normal"
        )

        self.start_http(server)

        return {
            "net": self.net,
            "server": server,
            "clients": hosts,
            "server_ip": self.server_ip,
        }

    # ------------------------------------------------------------------------
    # Serveur HTTP statique avec support HTTP Range
    # ------------------------------------------------------------------------

    def start_http(self, server):

        root = (
            Path(__file__)
            .resolve()
            .parents[1]
            / "htdocs"
        )

        if not root.exists():
            raise RuntimeError(f"Répertoire HTTP introuvable : {root}")

        server_script = "/tmp/range_http_server.py"

        # ----------------------------------------------------------------
        # Nettoyage d'un éventuel ancien serveur dans le namespace Mininet.
        # ----------------------------------------------------------------

        server.cmd("pkill -f 'python3 -m http.server 8000' 2>/dev/null || true")
        server.cmd("pkill -f 'range_http_server.py' 2>/dev/null || true")

        time.sleep(0.2)

        # ----------------------------------------------------------------
        # Serveur HTTP embarqué.
        #
        # SimpleHTTPRequestHandler.__init__(..., directory=ROOT) est
        # utilisé pour que les chemins HTTP soient réellement résolus
        # dans htdocs.
        #
        # Les requêtes Range retournent :
        #   HTTP 206 Partial Content
        #   Content-Range
        #   Content-Length
        #   Accept-Ranges: bytes
        #
        # Les requêtes normales continuent de fonctionner comme avant.
        # ----------------------------------------------------------------

        script = r'''
import http.server
import os
import re
import socketserver
import sys

ROOT = os.path.abspath(sys.argv[1])


class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        # Force explicitement htdocs comme racine du serveur.
        super().__init__(*args, directory=ROOT, **kwargs)

    def send_head(self):

        path = self.translate_path(self.path)

        if not os.path.isfile(path):
            return super().send_head()

        file_size = os.path.getsize(path)

        range_header = self.headers.get("Range")

        # Pas de Range : comportement HTTP statique normal.
        if not range_header:
            return super().send_head()

        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())

        # Range non supporté / mal formé.
        if not match:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None

        start_str, end_str = match.groups()

        # ----------------------------------------------------------------
        # bytes=N-M ou bytes=N-  (début explicite)
        # ----------------------------------------------------------------
        if start_str:
            start = int(start_str)

            if end_str:
                end = int(end_str)
            else:
                end = file_size - 1

        # ----------------------------------------------------------------
        # bytes=-N  (suffixe : les N derniers octets)
        # ----------------------------------------------------------------
        else:
            if not end_str:
                self.send_error(416, "Requested Range Not Satisfiable")
                return None

            length = int(end_str)

            if length <= 0:
                self.send_error(416, "Requested Range Not Satisfiable")
                return None

            start = max(file_size - length, 0)
            end = file_size - 1

        # ----------------------------------------------------------------
        # Validation.
        # ----------------------------------------------------------------

        if start >= file_size:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None

        end = min(end, file_size - 1)

        if end < start:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None

        content_length = end - start + 1

        self.range_start = start
        self.range_end = end

        # ----------------------------------------------------------------
        # Réponse HTTP 206.
        # ----------------------------------------------------------------

        self.send_response(206)
        self.send_header("Content-type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header(
            "Last-Modified",
            self.date_time_string(os.path.getmtime(path))
        )
        self.end_headers()

        return open(path, "rb")

    def do_GET(self):

        self.range_start = None
        self.range_end = None

        file_object = self.send_head()

        if file_object is None:
            return

        try:
            # ----------------------------------------------------------------
            # Réponse partielle.
            # ----------------------------------------------------------------
            if self.range_start is not None and self.range_end is not None:

                file_object.seek(self.range_start)

                remaining = self.range_end - self.range_start + 1

                while remaining > 0:
                    chunk = file_object.read(min(64 * 1024, remaining))

                    if not chunk:
                        break

                    self.wfile.write(chunk)
                    remaining -= len(chunk)

            # ----------------------------------------------------------------
            # Réponse complète normale.
            # ----------------------------------------------------------------
            else:
                self.copyfile(file_object, self.wfile)

        finally:
            file_object.close()


    def do_PUT(self):
        # Support minimal pour les scénarios d'upload : accepte le
        # corps de la requête, le consomme entièrement (pour que le
        # client considère l'envoi comme terminé), ne le stocke pas
        # sur disque (pas besoin pour mesurer le temps de transfert).
        content_length = int(self.headers.get("Content-Length", 0))

        remaining = content_length
        while remaining > 0:
            chunk = self.rfile.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


server = ThreadingHTTPServer(("0.0.0.0", 8000), RangeHTTPRequestHandler)
server.serve_forever()
'''

        # ----------------------------------------------------------------
        # Écrire le script directement depuis ce processus Python, sans
        # passer par server.cmd().
        #
        # Les hôtes Mininet ne sont isolés qu'au niveau réseau (network
        # namespace) : ils partagent le même système de fichiers que le
        # processus qui pilote la topologie. Passer par server.cmd()
        # pour écrire un gros blob (base64 ou autre) est fragile car les
        # commandes transitent par un pseudo-terminal dont la ligne
        # canonique est limitée (~4096 octets sous Linux) : une commande
        # plus longue est tronquée/corrompue silencieusement, ce qui
        # explique le "No such file or directory" précédent malgré une
        # commande apparemment correcte.
        #
        # Ecrire le fichier nous-mêmes élimine complètement ce problème.
        # ----------------------------------------------------------------

        try:
            with open(server_script, "w") as f:
                f.write(script)
        except OSError as exc:
            raise RuntimeError(
                f"Impossible d'écrire {server_script} : {exc}"
            ) from exc

        # ----------------------------------------------------------------
        # Vérifier que le fichier généré est syntaxiquement valide, ici
        # aussi directement en Python plutôt que via server.cmd().
        # ----------------------------------------------------------------

        import py_compile

        try:
            py_compile.compile(server_script, doraise=True)
        except py_compile.PyCompileError as exc:
            raise RuntimeError(
                "Le serveur HTTP généré contient une erreur Python :\n"
                f"{exc}"
            ) from exc

        # ----------------------------------------------------------------
        # Lancement du serveur.
        # ----------------------------------------------------------------

        server.cmd(
            f"python3 {server_script} '{root}' > /tmp/http.log 2>&1 &"
        )

        time.sleep(0.5)

        # ----------------------------------------------------------------
        # Vérification de disponibilité.
        #
        # On teste directement un fichier réel plutôt qu'un répertoire
        # arbitraire, pour éviter qu'un 404 sur /pdf/ soit confondu avec
        # un serveur HTTP fonctionnel.
        # ----------------------------------------------------------------

        pdf_dir = root / "pdf"
        pdf_files = list(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []

        if pdf_files:
            from urllib.parse import quote as _quote
            test_file = f"/pdf/{_quote(pdf_files[0].name, safe='')}"
        else:
            test_file = "/"

        check = server.cmd(
            "curl -s -o /dev/null -w '%{http_code}' "
            f"'http://127.0.0.1:8000{test_file}'"
        )

        if not check.strip().startswith(("2", "3")):
            raise RuntimeError(
                f"Le serveur HTTP ne répond pas sur "
                f"{self.server_host}:8000 (code reçu: {check!r}).\n"
                f"Racine HTTP : {root}\n"
                f"Contenu de /tmp/http.log :\n"
                f"{server.cmd('cat /tmp/http.log')}"
            )