# Le RAG du rapport, expliqué simplement

Ce document explique, **sans prérequis**, ce qu'est un *RAG* et comment nous l'avons
construit pour permettre au chatbot de répondre à partir du rapport d'audit (245 pages).

## C'est quoi un RAG ?

**RAG** = *Retrieval-Augmented Generation* (« génération augmentée par la
recherche »). L'idée tient en une phrase :

> Au lieu de demander au modèle de langage de répondre « de mémoire » (ce qu'il
> ferait en inventant parfois), on **retrouve d'abord les passages pertinents du
> document**, puis on les **donne au modèle** pour qu'il rédige une réponse fondée
> sur ces extraits — en **citant ses sources**.

Analogie : un étudiant à un examen « livre ouvert ». Il ne récite pas par cœur ; il
**ouvre le bon chapitre**, lit le passage utile, puis répond avec ses mots en
indiquant la page. Le RAG fait pareil, automatiquement.

Cela répond directement à notre principe directeur : *le LLM ne doit pas inventer ;
il s'appuie sur des sources vérifiables*.

---

## Le problème : retrouver « le bon passage »

Un mot-clé exact (Ctrl-F) ne suffit pas. Si l'utilisateur demande
« pourquoi les pompes à chaleur sous-performent ? », le rapport parle peut-être de
« écarts au SCOP constructeur », « défauts d'équilibrage hydraulique »,
« régulation »… sans le mot « sous-performent ». Il faut une recherche **par le
sens**, pas par les lettres. C'est ce que permettent les **embeddings**.

---

## Phase 1 — Indexation (faite une fois, hors ligne)

C'est la préparation : on transforme le PDF en une **base interrogeable par le sens**.
Script : [`backend/scripts/build-index`](../backend/scripts/build-index)
(module [`chatbot.rag.index`](../backend/src/chatbot/rag/index.py)).

```
PDF ──(1)──> texte par page ──(2)──> fragments ──(3)──> vecteurs ──(4)──> base Chroma
```

### (1) Extraction du texte

[`chatbot.rag.extract`](../backend/src/chatbot/rag/extract.py) lit le PDF page par
page (bibliothèque **PyMuPDF**) et récupère le texte. On garde au passage le **numéro
de page** et, comme le PDF n'a pas de signets, on **devine la section** courante en
repérant les titres (« 2.3 … », titres en capitales). Ces métadonnées serviront à
**citer la source**.

### (2) Découpage en fragments (chunking)

Une page entière est trop grosse et mélange plusieurs idées. On la coupe en
**fragments** d'environ 1 200 caractères, avec un **chevauchement** de 200 caractères
entre fragments voisins (pour ne pas couper une idée en plein milieu). Outil :
`RecursiveCharacterTextSplitter`. Résultat sur notre rapport : **564 fragments**,
chacun étiqueté avec sa page et sa section.

> **Tokenisation ?** Les modèles ne lisent pas des caractères mais des *tokens* :
> des unités qui sont souvent des **sous-mots**. Un mot courant est généralement un
> seul token, tandis qu'un mot rare ou long peut être découpé en plusieurs morceaux.
> Le découpage exact n'est pas universel : il dépend du *tokenizer* propre à chaque
> modèle (Mistral a le sien). Le token est l'unité que comptent les modèles (et la
> facturation). Notre découpage en fragments est fait en **caractères** par
> simplicité, mais l'idée est la même : produire des morceaux de taille raisonnable.

### (3) Embeddings : transformer le texte en vecteurs

Chaque fragment est envoyé au modèle **`mistral-embed`**, qui renvoie un **vecteur** :
une liste d'environ **1 024 nombres** qui « résume » le sens du fragment. Propriété
clé :

> Deux textes au **sens proche** ont des vecteurs **proches** dans l'espace ; deux
> textes sans rapport ont des vecteurs éloignés.

On peut imaginer une immense carte où chaque fragment est un point : les passages sur
les COP sont regroupés dans une zone, ceux sur le recrutement de l'échantillon dans
une autre, etc. La « distance » entre deux points mesure leur proximité de sens
(typiquement la **similarité cosinus**).

### (4) Stockage dans Chroma

[**Chroma**](https://www.trychroma.com/) est une **base de données vectorielle** :
elle stocke les vecteurs **et** leurs métadonnées (texte, page, section) et sait
retrouver très vite les vecteurs les plus proches d'un vecteur donné. Chez nous elle
est persistée sur disque dans `backend/store/chroma` (techniquement un fichier
SQLite + index). On crée **deux collections** :

- `rapport_pac` — les 564 fragments de texte ;
- `rapport_figures` — les **légendes** des ~235 figures/tableaux (pour l'outil qui
  affiche une figure).

À ce stade, le rapport est « digéré » : prêt à être interrogé par le sens.

---

## Phase 2 — Inférence (à chaque question)

Quand l'utilisateur pose une question, l'outil
[`search_report`](../backend/src/chatbot/tools/report.py) fait :

```
question ──embed──> vecteur ──recherche top-k──> 4 fragments + (page, section)
                                                        │
                                          passés au LLM (Mistral)
                                                        │
                              réponse rédigée + citation des pages
```

1. **La question est transformée en vecteur** par le même modèle `mistral-embed`.
2. **Recherche des plus proches** (`similarity_search`, k=4) : Chroma renvoie les 4
   fragments dont le vecteur est le plus proche de celui de la question — donc les
   plus pertinents *par le sens*.
3. **Augmentation** : ces 4 passages (avec leur page) sont fournis au modèle Mistral,
   accompagnés de la consigne « réponds uniquement à partir de ces extraits et cite
   la page ».
4. **Génération** : le modèle rédige une réponse synthétique et **cite ses sources**
   (page/section), affichées dans l'interface sous l'indicateur 📑.

Le modèle ne « connaît » donc pas le rapport : il **reçoit** à chaque fois juste ce
qu'il faut. Avantages :

- **Pas d'hallucination** : la réponse s'appuie sur des extraits réels.
- **Traçabilité** : on sait d'où vient chaque affirmation (page).
- **Sobriété** : on n'envoie au modèle que 4 petits passages, pas les 245 pages — le
  contexte reste petit et peu coûteux (un de nos principes directeurs : *les données
  ne transitent pas en masse par le modèle*).

---

## Et pour les figures ?

Même principe, appliqué aux **légendes** : la question est comparée aux légendes
indexées (`rapport_figures`), on identifie la figure la plus proche, puis on **rend
la page** du PDF en image pour l'afficher (outil `show_report_figure`). Cf.
[`chatbot.rag.figures`](../backend/src/chatbot/rag/figures.py).

---

## Mini-glossaire

| Terme | En une phrase |
|-------|----------------|
| **Token** | Petit morceau de texte (souvent un bout de mot) que le modèle manipule. |
| **Embedding** | Vecteur de nombres qui représente le *sens* d'un texte. |
| **Chunk / fragment** | Morceau de document de taille raisonnable, indexé séparément. |
| **Base vectorielle** | Base de données qui retrouve les vecteurs les plus proches (Chroma). |
| **Similarité cosinus** | Mesure de proximité entre deux vecteurs (= proximité de sens). |
| **top-k** | On garde les *k* résultats les plus proches (ici k = 4). |
| **RAG** | Retrouver les bons passages, puis générer une réponse fondée sur eux. |

## Pour aller plus loin (dans ce repo)

- Construire l'index : `cd backend && scripts/build-index`.
- Code : [`rag/extract.py`](../backend/src/chatbot/rag/extract.py),
  [`rag/index.py`](../backend/src/chatbot/rag/index.py),
  [`tools/report.py`](../backend/src/chatbot/tools/report.py).
- Choix d'implémentation et chiffres : [devlog.md](devlog.md) (Phase 2).
