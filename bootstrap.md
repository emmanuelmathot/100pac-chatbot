# 100 PAC

## Project Overview

Enertech scop, une entreprise spécialisée dans la thermique et l'énergie des batiments a effectué un audit énergétique sur 90 pompes à chaleur air/eau et 10 pompes à chaleur géothermiques qui ont été instrumentées afin de connaitre leurs performances réelles. Ces PAC ont toutes remplacé des chaudières gaz ou fioul dans des maisons individuelles. 

Ce rapport présente l'ensemble des résultats et enseignements obtenus.  il se trouve ici: docs/Performance-PAC-Rapport-final.pdf
L'ensemble des mesures se trouve dans data/log_002026.xlsx

Je voudrais créer un chatbot qui puisse répondre à des questions sur le rapport et les mesures. Le chatbot devra être capable de répondre à des questions telles que "Quelle est la performance moyenne des PAC air/eau ?" ou "Quels sont les résultats de l'audit pour les PAC géothermiques ?". Ce sera un chatbot agentic avec des capacités de recherche et d'analyse de données.

## Application

un squelette d'application est disponible dans le dossier chatbot skeleton. Il contient un exemple de code pour créer un chatbot qui peut répondre à des questions sur le rapport et les mesures. Le code utilise la bibliothèque LangChain pour gérer les interactions avec l'utilisateur et effectuer des recherches dans les données.

Il faudra développer le code pour que le chatbot puisse répondre aux questions sur le rapport et les mesures. Le chatbot devra être capable de comprendre les questions de l'utilisateur, de rechercher les informations pertinentes dans le rapport et les mesures, et de fournir des réponses précises et complètes.

## Prerequis - Préparation des données

Les données sont disponibles dans le fichier data/log_002026.xlsx. un des objectifs majeurs de ce projet est de créer un modele de données basé sur Zarr qui permettra de stocker les données de manière efficace sur plusieurs dimensions. Le format Zarr est un format de stockage de données en colonnes qui permet de stocker des données volumineuses de manière efficace et de les accéder rapidement. Les indexations multi-dimensionnelles permettent de répondre rapidement à des requêtes complexes sur les données.

## Le rapport d'audit énergétique

Il faudra trouver un moyen de rendre le rapport d'audit énergétique accessible au chatbot. Le rapport est disponible dans le fichier docs/Performance-PAC-Rapport-final.pdf. Il faudra extraire les informations pertinentes du rapport et les stocker dans un format qui permettra au chatbot de les utiliser pour répondre aux questions de l'utilisateur. Certaines informations du rapport peuvent être extraites sous forme de texte, tandis que d'autres informations peuvent être extraites sous forme de tableaux ou de graphiques. Il faudra trouver un moyen de stocker ces informations de manière efficace pour que le chatbot puisse y accéder rapidement.

## Plan d'implémentation

Il faudra créer un plan d'implémentation pour le chatbot. Le plan d'implémentation devra inclure les étapes suivantes :
1. Préparation des données : il faudra préparer les données en les convertissant dans un format qui permettra au chatbot de les utiliser pour répondre aux questions de l'utilisateur. Il faudra également créer un modèle de données basé sur Zarr pour stocker les données de manière efficace sur plusieurs dimensions.
2. Extraction des informations du rapport : il faudra extraire les informations pertinentes du rapport d'audit énergétique et les stocker dans un format qui permettra au chatbot de les utiliser pour répondre aux questions de l'utilisateur. Il faudra également créer un modèle de données basé sur Zarr pour stocker les informations du rapport de manière efficace sur plusieurs dimensions.
3. Développement du chatbot : il faudra développer le chatbot en utilisant la bibliothèque LangChain pour gérer les interactions avec l'utilisateur et effectuer des recherches dans les données. Le chatbot devra être capable de comprendre les questions de l'utilisateur, de rechercher les informations pertinentes dans les données et le rapport, et de fournir des réponses précises et complètes.
4. Test et validation : il faudra tester le chatbot pour s'assurer qu'il fonctionne correctement et qu'il fournit des réponses précises et complètes aux questions de l'utilisateur. Il faudra également valider les résultats du chatbot en les comparant aux résultats obtenus par les analystes humains pour s'assurer que le chatbot fournit des réponses précises et complètes aux questions de l'utilisateur.

Tout sera documenté dans le dossier docs avec un devlog et sera versionné sur git. Le code sera également documenté avec des commentaires pour expliquer le fonctionnement du chatbot et les étapes de l'implémentation.

A la fin, il faudra pouvoir déployer le chatbot sur un serveur pour qu'il soit accessible aux utilisateurs pour tester le chatbot et pour qu'il puisse répondre aux questions des utilisateurs sur le rapport et les mesures. Il faudra également créer une interface utilisateur pour le chatbot afin que les utilisateurs puissent interagir avec le chatbot de manière conviviale et intuitive.

Un chart helm sera créé pour déployer le chatbot sur un cluster Kubernetes. Le chart helm contiendra les fichiers de configuration nécessaires pour déployer le chatbot sur un cluster Kubernetes, y compris les fichiers de configuration pour les services, les déploiements et les volumes persistants. Le chart helm permettra également de configurer les paramètres du chatbot, tels que le port d'écoute et les paramètres de connexion à la base de données.