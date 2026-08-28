# Meaningful Connectivity — Explainable Assessment

Projet de stage consacré à l'évaluation explicable de la **Meaningful Connectivity** dans le contexte des services éducatifs soumis à des conditions de faible connectivité.

L'objectif est de construire une chaîne permettant de :

1. collecter des observations de sessions réseau ;
2. déterminer si une session est `meaningful` ou `not meaningful` ;
3. entraîner et comparer plusieurs modèles de classification ;
4. expliquer les décisions du modèle avec des techniques d'IA explicable, notamment **SHAP** ;
5. exposer les fonctionnalités utiles au travers d'une API.

> **Périmètre :** ce dépôt correspond au sous-projet consacré à l'IA explicable et à l'évaluation intelligente de la Meaningful Connectivity. Les simulations réseau servent principalement à produire les données expérimentales nécessaires à l'entraînement et à la comparaison des modèles.

---

## Architecture

Le projet est organisé en trois composants principaux.

```text
meaningful-connectivity/
│
├── api/                    # Interface HTTP
│
├── models/                 # Machine Learning et XAI
│
├── simulation/             # Génération expérimentale des données
│
├── README.md
├── requirements.txt
└── .gitignore
```

### `simulation/`

Contient tout ce qui concerne la génération des données expérimentales et l'environnement Mininet.

```text
simulation/
├── scenarios/
├── network/
├── measurement/
├── runner/
├── audit/
└── htdocs/
```

Le dossier `scenarios/` contient les scénarios applicatifs utilisés pour représenter différents usages pédagogiques.

Le dossier `network/` contient les éléments liés à la topologie et à la configuration réseau.

`measurement/` regroupe les mécanismes de collecte des métriques réseau et applicatives.

`runner/` contient les mécanismes d'exécution des campagnes de simulation.

`audit/` contient les outils permettant de contrôler la cohérence, la qualité et la reproductibilité des données générées.

`htdocs/` contient les ressources servies par les scénarios de téléchargement. Les ressources réelles ne sont pas versionnées lorsqu'elles contiennent des fichiers personnels ou volumineux.

Voir [`simulation/htdocs/README.md`](simulation/htdocs/README.md) pour le contrat attendu.

---

## `models/`

Ce module constitue le cœur Machine Learning et XAI du projet.

```text
models/
├── config.py
├── data_loader.py
├── preprocessing.py
├── train.py
├── evaluate.py
├── run_experiments.py
├── explain.py
└── explanations/
```

### Chargement des données

`data_loader.py` charge le dataset tabulaire et vérifie la présence des colonnes nécessaires.

La variable cible est :

```text
meaningful
```

avec :

```text
0 → not meaningful
1 → meaningful
```

Les features actuellement utilisées sont :

```text
bandwidth
concurrent_users
deadline_seconds
interaction_level
jitter
latency
packet_loss
resource_size_mb
service_type
```

### Prétraitement

`preprocessing.py` utilise un `ColumnTransformer`.

Les variables numériques peuvent être :

* imputées par la médiane ;
* standardisées pour les modèles qui le nécessitent.

`service_type` est traité comme variable catégorielle avec :

* imputation par la modalité la plus fréquente ;
* One-Hot Encoding ;
* `handle_unknown="ignore"`.

Le prétraitement est intégré directement aux pipelines scikit-learn afin d'éviter les incohérences entre entraînement et inférence.

### Modèles

Trois modèles sont actuellement implémentés :

* Logistic Regression ;
* Random Forest ;
* HistGradientBoostingClassifier.

La comparaison utilise notamment :

* Accuracy ;
* Precision ;
* Recall ;
* F1-score ;
* ROC-AUC ;
* matrice de confusion.

Les paramètres expérimentaux sont centralisés dans `models/config.py`.

### Explainable AI

`explain.py` constitue la couche d'explicabilité.

SHAP est utilisé pour produire notamment :

* des explications globales ;
* l'importance des variables ;
* des explications locales ;
* des visualisations permettant d'interpréter les décisions individuelles du modèle.

L'implémentation prend en compte le fait que les différents modèles ne sont pas expliqués par le même explainer SHAP : les modèles arborescents peuvent notamment utiliser `TreeExplainer`, tandis que les modèles d'une autre famille nécessitent une méthode appropriée à leur fonctionnement.

Les résultats graphiques sont générés dans :

```text
models/explanations/
```

---

## API

`api/` constitue la couche d'accès externe au système.

Elle **ne contient pas de logique Machine Learning**.

Son rôle est notamment de :

* charger les modèles disponibles ;
* demander une prédiction ;
* demander une explication ;
* exposer les résultats sous forme JSON ;
* déclencher, lorsque cela est nécessaire, les fonctions déjà présentes dans `models/`.

L'API est conçue pour rester découplée de l'implémentation interne des modèles.

Une évolution prévue est de permettre la gestion du cycle de vie expérimental :

```text
chargement des données
        ↓
entraînement
        ↓
évaluation
        ↓
sélection / validation du modèle
        ↓
enregistrement d'une version
        ↓
utilisation pour l'inférence
```

La logique correspondante reste toutefois dans `models/`; l'API ne fait qu'orchestrer les appels.

---

## Données expérimentales

Les données utilisées par le projet sont issues de simulations contrôlées.

La génération expérimentale permet notamment de faire varier les conditions réseau et les caractéristiques applicatives afin d'observer leur influence sur le caractère `meaningful` d'une session.

Le dataset expérimental actuellement disponible a déjà dépassé le millier d'observations.

Une campagne précédente comportait notamment :

```text
Observations : 1051
Features     : 9

meaningful     : 601
not meaningful : 450
```

Les résultats obtenus avec une séparation entraînement/test de 80/20 ont notamment montré :

| Modèle               | Accuracy | Precision | Recall |     F1 | ROC-AUC |
| -------------------- | -------: | --------: | -----: | -----: | ------: |
| Logistic Regression  |   0.8199 |    0.7862 | 0.9421 | 0.8571 |  0.8919 |
| Random Forest        |   0.8863 |    0.8702 | 0.9421 | 0.9048 |  0.9252 |
| HistGradientBoosting |   0.8863 |    0.8489 | 0.9752 | 0.9077 |  0.9483 |

Ces résultats sont expérimentaux et ne constituent pas une validation définitive du modèle final.

---

## Reproductibilité et audit

Les simulations utilisent des paramètres contrôlés et des seeds lorsque cela est nécessaire afin de rendre les expériences reproductibles.

Les données générées sont accompagnées de traces expérimentales permettant de confronter :

* les paramètres de simulation ;
* les métriques réseau ;
* les métriques applicatives ;
* le résultat observé ;
* le label finalement attribué.

Des scripts d'audit ont également été développés pour vérifier la cohérence du dataset et détecter des anomalies dans les observations.

---

## Installation

Les dépendances Python sont installables avec :

```bash
python3 -m pip install --user -r requirements.txt
```

Mininet n'est pas installé par `pip` et doit être installé séparément au niveau système.

---

## Exécution du Machine Learning

Comparaison des modèles :

```bash
python3 -m models.run_experiments
```

Génération des explications SHAP :

```bash
python3 -m models.explain
```

---

## Données et ressources non versionnées

Les datasets expérimentaux et les ressources volumineuses ou personnelles ne sont pas nécessairement inclus dans le dépôt Git.

Le dépôt conserve uniquement les éléments nécessaires pour comprendre, reproduire et exploiter l'architecture.

En particulier, les fichiers personnels placés dans `simulation/htdocs/` ne doivent pas être publiés.

---

## État du projet

Le projet est en cours d'expérimentation.

Les modèles, features, scénarios et paramètres expérimentaux peuvent encore évoluer avant la validation finale.

Les résultats actuellement présents dans le dépôt doivent donc être considérés comme des résultats expérimentaux intermédiaires.
