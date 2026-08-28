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
