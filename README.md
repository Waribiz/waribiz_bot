Bot Telegram de Publications Automatiques Facebook
Ce bot Telegram vous permet de générer et publier automatiquement du contenu sur votre page Facebook. Il utilise l'API d'OpenAI pour générer des messages engageants et peut être entièrement contrôlé via une interface Telegram conviviale.
Fonctionnalités

🚀 Génération automatique de contenu avec l'API OpenAI (GPT-4o-mini)
📱 Interface interactive avec boutons dans Telegram
⏱️ Planification flexible des publications (intervalle personnalisable)
🎯 Thèmes personnalisables pour orienter le contenu généré
📊 Suivi des publications avec enregistrement dans un fichier CSV
🖼️ Support des images (aléatoires depuis un dossier ou URL par défaut)
🔄 Publication manuelle ou automatique selon vos besoins

Prérequis

Python 3.8+
Un token pour un bot Telegram (obtenu via @BotFather)
Un token d'accès pour une Page Facebook
Une clé API OpenAI

Installation

Clonez ce dépôt ou téléchargez le fichier source
Installez les dépendances requises :

pip install python-telegram-bot python-dotenv requests openai

Créez un fichier .env dans le même répertoire avec les informations suivantes :

TELEGRAM_BOT_TOKEN=votre_token_bot_telegram
PAGE_ACCESS_TOKEN=votre_token_facebook_page
PAGE_ID=votre_id_page_facebook
OPENAI_API_KEY=votre_clé_api_openai
THEME=thème_par_défaut
INTERVAL_MINUTES=60

Créez un dossier images pour y placer les images que vous souhaitez utiliser pour vos publications (optionnel)

Utilisation

Démarrez le bot :

python telegram_bot.py

Ouvrez Telegram et commencez une conversation avec votre bot
Utilisez la commande /start pour afficher le menu principal

Commandes disponibles

/start - Démarre le bot et affiche le menu principal
/help - Affiche l'aide du bot
/set_openai_key VOTRE_CLÉ - Configure la clé API OpenAI
/set_page_token VOTRE_TOKEN - Configure le token d'accès Facebook
/set_page_id VOTRE_ID - Configure l'ID de la page Facebook
/set_interval MINUTES - Définit l'intervalle entre les publications

Menu principal
Le menu principal propose plusieurs options accessibles par boutons :

📊 Statut - Affiche la configuration actuelle du bot
🔄 Publier maintenant - Génère et publie immédiatement un nouveau post
▶️ Démarrer auto - Active les publications automatiques
⏹️ Arrêter auto - Désactive les publications automatiques
🔧 Paramètres - Accède aux options de configuration

Menu des paramètres

🏷️ Changer le thème - Modifie le thème utilisé pour générer le contenu
⏱️ Changer l'intervalle - Modifie le temps entre les publications automatiques
🔑 Configurer API - Instructions pour configurer l'API OpenAI
📄 Configurer Facebook - Instructions pour configurer l'accès Facebook

Structure des publications
Les publications générées sont optimisées pour promouvoir un bot Telegram de pronostics football, avec :

Un emoji d'accroche au début
Une promesse de valeur (gratuité, exclusivité, etc.)
Un appel à l'action clair
Le lien vers le bot Telegram
Une longueur optimale pour l'engagement

Sécurité

Les tokens et clés API sont stockés localement dans le fichier .env
Les messages contenant des informations sensibles sont supprimés après traitement
Les erreurs sont consignées mais n'exposent pas d'informations sensibles

Dépannage
Le bot ne démarre pas

Vérifiez que le token Telegram est correct
Assurez-vous que toutes les dépendances sont installées

Les publications échouent

Vérifiez que le token Facebook et l'ID de page sont corrects
Assurez-vous que le token Facebook a les autorisations nécessaires

La génération de contenu échoue

Vérifiez que la clé API OpenAI est valide
Vérifiez votre connexion internet

Personnalisation avancée
Le bot peut être personnalisé en modifiant directement le code source :

Changez le prompt OpenAI pour adapter le style des messages
Modifiez la structure des boutons et menus
Ajoutez de nouvelles fonctionnalités comme la programmation à des heures spécifiques

Contribuer
Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.
Licence
Ce projet est distribué sous licence MIT. Voir le fichier LICENSE pour plus d'informations.