# Ressources HTTP des simulations

Ce répertoire contient les ressources statiques utilisées par les scénarios de simulation réseau.

Les fichiers peuvent notamment être utilisés pour représenter des ressources pédagogiques telles que :

* documents PDF ;
* pages HTML ;
* images ;
* fichiers audio ;
* fichiers vidéo ;
* autres ressources téléchargées par les clients Mininet.

## Important

Les ressources réelles utilisées localement ne sont **pas nécessairement versionnées**.

En particulier, ce répertoire peut contenir des fichiers personnels, des fichiers volumineux ou des ressources utilisées uniquement pour les expérimentations locales.

**Ne jamais publier une ressource personnelle ou confidentielle dans le dépôt Git.**

---

## Structure

Les scénarios peuvent organiser les ressources par type :

```text
htdocs/
├── pdf/
├── html/
├── images/
├── audio/
├── video/
└── ...
```

Chaque scénario est responsable de connaître le sous-répertoire correspondant à son type de ressource.

Par exemple :

```text
simulation/scenarios/pdf.py
        ↓
simulation/htdocs/pdf/
```

---

## Ressources PDF

Le scénario PDF découvre automatiquement les fichiers présents dans :

```text
htdocs/pdf/
```

Les fichiers sont triés par nom afin de garantir un ordre déterministe lors de la sélection d'une ressource.

Un fichier peut par exemple être placé localement ainsi :

```text
htdocs/
└── pdf/
    ├── cours_01.pdf
    ├── cours_02.pdf
    └── cours_03.pdf
```

Le scénario récupère notamment :

* le nom du fichier ;
* sa taille en octets ;
* sa taille en mégaoctets.

La taille réelle du fichier constitue une information de référence pour vérifier la complétude d'un téléchargement.

---

## Serveur HTTP

Les ressources sont servies par le serveur HTTP utilisé dans l'environnement de simulation.

Les clients Mininet accèdent aux ressources via une URL du type :

```text
http://<server-ip>:8000/<resource-path>
```

Le détail du serveur et de son lancement appartient à la couche `simulation/` et non à ce répertoire.

---

## Reproduction d'une expérience

Pour reproduire une campagne nécessitant des ressources locales :

1. récupérer ou créer les ressources nécessaires ;
2. les placer dans les sous-répertoires attendus ;
3. vérifier leurs tailles ;
4. lancer la campagne de simulation.

Les ressources ne sont pas considérées comme faisant partie du dataset ML lui-même : elles servent à provoquer les conditions applicatives dont les métriques seront ensuite collectées.

## Ressources calibrées de l'agent IA

Le scénario `ai_agent` dispose de six tâches locales calibrées autour de la
frontière de décision, générées à la demande afin de ne pas versionner les
binaires :

```bash
python3 simulation/fixtures/generate_agent_resources.py
```

Les tâches `task_tiny_a/b`, `task_small_a/b`, `task_medium_a/b`,
`task_light_a/b`, `task_target_a/b` et `task_heavy_a/b` couvrent environ
10 %, 20 %, 30 %, 50 %, 100 % et 180 % de la cible de transfert. Les trois
premiers niveaux ajoutent des cas susceptibles de réussir même lorsque le
débit est partagé entre plusieurs clients. Chaque tâche contient deux
rafales de lecture parallèles et deux écritures séquentielles. La graine `42`
garantit des tailles reproductibles.
