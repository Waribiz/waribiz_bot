import os
import time
import random
import csv
import datetime
import requests
import asyncio
import logging
import json
from urllib.parse import urlencode
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import JobQueue
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    ConversationHandler
)

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# États de conversation
THEME, INTERVAL, WAITING_FOR_THEME, WAITING_FOR_INTERVAL = range(4)

# Charger les variables d'environnement
load_dotenv()

# Configuration par défaut
DEFAULT_CONFIG = {
    'THEME': 'promo du bot MATCH_PREDICTION_AI',
    'INTERVAL_MINUTES': 60,
    'IMAGES_FOLDER': 'images',
    'MESSAGES_CSV': 'messages.csv',
    'USERS_CSV': 'users.csv',
    'AUTO_POST_ENABLED': False,
    'FACEBOOK_APP_ID': os.getenv('FACEBOOK_APP_ID', ''),
    'FACEBOOK_APP_SECRET': os.getenv('FACEBOOK_APP_SECRET', ''),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
    'ADMIN_TELEGRAM_ID': os.getenv('ADMIN_TELEGRAM_ID', '')
}

# Liens pour l'authentification Facebook
FACEBOOK_OAUTH_URL = "https://www.facebook.com/v22.0/dialog/oauth"
FACEBOOK_GRAPH_URL = "https://graph.facebook.com/v22.0"
REDIRECT_URI = os.getenv('REDIRECT_URI', 'https://your-redirect-uri.com/facebook_callback')

# Dictionnaire pour stocker les configurations spécifiques à chaque utilisateur
USER_CONFIGS = {}

def initialize_csv_files():
    """Initialise les fichiers CSV s'ils n'existent pas"""
    # Fichier des messages
    if not os.path.exists(DEFAULT_CONFIG['MESSAGES_CSV']):
        with open(DEFAULT_CONFIG['MESSAGES_CSV'], 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['user_id', 'id_post', 'message', 'date_post'])
            writer.writeheader()
            logger.info(f"Fichier CSV '{DEFAULT_CONFIG['MESSAGES_CSV']}' créé.")
    
    # Fichier des utilisateurs
    if not os.path.exists(DEFAULT_CONFIG['USERS_CSV']):
        with open(DEFAULT_CONFIG['USERS_CSV'], 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['telegram_id', 'page_id', 'page_name', 'long_lived_token', 'token_expiry', 'theme', 'interval_minutes', 'auto_post_enabled'])
            writer.writeheader()
            logger.info(f"Fichier CSV '{DEFAULT_CONFIG['USERS_CSV']}' créé.")

def load_users_data():
    """Charge les données des utilisateurs depuis le CSV"""
    if not os.path.exists(DEFAULT_CONFIG['USERS_CSV']):
        return
    
    with open(DEFAULT_CONFIG['USERS_CSV'], 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            user_id = row['telegram_id']
            USER_CONFIGS[user_id] = {
                'PAGE_ID': row['page_id'],
                'PAGE_NAME': row['page_name'],
                'PAGE_ACCESS_TOKEN': row['long_lived_token'],
                'TOKEN_EXPIRY': row['token_expiry'],
                'THEME': row['theme'] or DEFAULT_CONFIG['THEME'],
                'INTERVAL_MINUTES': int(row['interval_minutes']) if row['interval_minutes'] else DEFAULT_CONFIG['INTERVAL_MINUTES'],
                'AUTO_POST_ENABLED': row['auto_post_enabled'].lower() == 'true',
                'OPENAI_API_KEY': DEFAULT_CONFIG['OPENAI_API_KEY']
            }
            logger.info(f"Données utilisateur chargées pour: {user_id}")

def save_user_data(telegram_id, page_id, page_name, long_lived_token, token_expiry, theme=None, interval_minutes=None, auto_post_enabled=None):
    """Enregistre ou met à jour les données d'un utilisateur dans le CSV"""
    user_exists = False
    rows = []
    
    # Lire les données existantes
    if os.path.exists(DEFAULT_CONFIG['USERS_CSV']):
        with open(DEFAULT_CONFIG['USERS_CSV'], 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['telegram_id'] == str(telegram_id):
                    # Mettre à jour les données existantes
                    row['page_id'] = page_id
                    row['page_name'] = page_name
                    row['long_lived_token'] = long_lived_token
                    row['token_expiry'] = token_expiry
                    if theme is not None:
                        row['theme'] = theme
                    if interval_minutes is not None:
                        row['interval_minutes'] = str(interval_minutes)
                    if auto_post_enabled is not None:
                        row['auto_post_enabled'] = str(auto_post_enabled).lower()
                    user_exists = True
                rows.append(row)
    
    # Ajouter un nouvel utilisateur si nécessaire
    if not user_exists:
        rows.append({
            'telegram_id': str(telegram_id),
            'page_id': page_id,
            'page_name': page_name,
            'long_lived_token': long_lived_token,
            'token_expiry': token_expiry,
            'theme': theme or DEFAULT_CONFIG['THEME'],
            'interval_minutes': str(interval_minutes or DEFAULT_CONFIG['INTERVAL_MINUTES']),
            'auto_post_enabled': str(auto_post_enabled or False).lower()
        })
    
    # Écrire les données mises à jour
    with open(DEFAULT_CONFIG['USERS_CSV'], 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['telegram_id', 'page_id', 'page_name', 'long_lived_token', 'token_expiry', 'theme', 'interval_minutes', 'auto_post_enabled'])
        writer.writeheader()
        writer.writerows(rows)
        
    # Mettre à jour les données en mémoire
    USER_CONFIGS[str(telegram_id)] = {
        'PAGE_ID': page_id,
        'PAGE_NAME': page_name,
        'PAGE_ACCESS_TOKEN': long_lived_token,
        'TOKEN_EXPIRY': token_expiry,
        'THEME': theme or DEFAULT_CONFIG['THEME'],
        'INTERVAL_MINUTES': int(interval_minutes or DEFAULT_CONFIG['INTERVAL_MINUTES']),
        'AUTO_POST_ENABLED': bool(auto_post_enabled or False),
        'OPENAI_API_KEY': DEFAULT_CONFIG['OPENAI_API_KEY']
    }
    
    logger.info(f"Données utilisateur enregistrées pour: {telegram_id}")

def update_user_config(telegram_id, key, value):
    """Met à jour une valeur spécifique dans la configuration d'un utilisateur"""
    user_id = str(telegram_id)
    
    # Vérifier si l'utilisateur existe
    if user_id not in USER_CONFIGS:
        logger.error(f"Tentative de mise à jour pour utilisateur inexistant: {user_id}")
        return False
    
    # Mettre à jour la valeur en mémoire
    USER_CONFIGS[user_id][key] = value
    
    # Mettre à jour le fichier CSV
    rows = []
    with open(DEFAULT_CONFIG['USERS_CSV'], 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['telegram_id'] == user_id:
                if key == 'THEME':
                    row['theme'] = value
                elif key == 'INTERVAL_MINUTES':
                    row['interval_minutes'] = str(value)
                elif key == 'AUTO_POST_ENABLED':
                    row['auto_post_enabled'] = str(value).lower()
            rows.append(row)
    
    with open(DEFAULT_CONFIG['USERS_CSV'], 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['telegram_id', 'page_id', 'page_name', 'long_lived_token', 'token_expiry', 'theme', 'interval_minutes', 'auto_post_enabled'])
        writer.writeheader()
        writer.writerows(rows)
    
    logger.info(f"Configuration mise à jour pour {user_id}: {key} = {value}")
    return True

def get_facebook_auth_url(telegram_id):
    """Génère l'URL d'authentification Facebook"""
    auth_params = {
        'client_id': DEFAULT_CONFIG['FACEBOOK_APP_ID'],
        'redirect_uri': REDIRECT_URI,
        'state': telegram_id,  # Pour identifier l'utilisateur lors du callback
        'scope': 'pages_show_list,pages_read_engagement,pages_manage_posts,pages_manage_metadata'
    }
    return f"{FACEBOOK_OAUTH_URL}?{urlencode(auth_params)}"

def exchange_code_for_token(code):
    """Échange le code d'autorisation contre un token"""
    token_params = {
        'client_id': DEFAULT_CONFIG['FACEBOOK_APP_ID'],
        'client_secret': DEFAULT_CONFIG['FACEBOOK_APP_SECRET'],
        'redirect_uri': REDIRECT_URI,
        'code': code
    }
    
    try:
        response = requests.get(f"{FACEBOOK_GRAPH_URL}/oauth/access_token", params=token_params)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        logger.error(f"Erreur lors de l'échange du code contre un token: {e}")
        return None

def get_long_lived_token(short_lived_token):
    """Obtient un token de longue durée à partir d'un token de courte durée"""
    if not short_lived_token:
        return None, None
    
    token_params = {
        'grant_type': 'fb_exchange_token',
        'client_id': DEFAULT_CONFIG['FACEBOOK_APP_ID'],
        'client_secret': DEFAULT_CONFIG['FACEBOOK_APP_SECRET'],
        'fb_exchange_token': short_lived_token
    }
    
    try:
        response = requests.get(f"{FACEBOOK_GRAPH_URL}/oauth/access_token", params=token_params)
        response.raise_for_status()
        data = response.json()
        
        # Calculer la date d'expiration (par défaut 60 jours)
        today = datetime.datetime.now()
        expiry_date = today + datetime.timedelta(days=60)
        
        return data.get('access_token'), expiry_date.strftime('%Y-%m-%d')
    except Exception as e:
        logger.error(f"Erreur lors de l'obtention du token de longue durée: {e}")
        return None, None

def get_user_pages(access_token):
    """Récupère les pages que l'utilisateur peut gérer"""
    if not access_token:
        return None
    
    try:
        response = requests.get(
            f"{FACEBOOK_GRAPH_URL}/me/accounts",
            params={'access_token': access_token}
        )
        response.raise_for_status()
        return response.json().get('data', [])
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des pages: {e}")
        return None

def save_post_to_csv(user_id, post_id, message, date_post):
    """Enregistre un post dans le CSV des messages"""
    with open(DEFAULT_CONFIG['MESSAGES_CSV'], 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['user_id', 'id_post', 'message', 'date_post'])
        writer.writerow({
            'user_id': user_id,
            'id_post': post_id,
            'message': message,
            'date_post': date_post
        })
        logger.info(f"Post enregistré dans le CSV pour l'utilisateur {user_id}")

def get_random_image():
    """Récupère une image aléatoire du dossier ou utilise une URL par défaut"""
    if os.path.exists(DEFAULT_CONFIG['IMAGES_FOLDER']):
        images = [f for f in os.listdir(DEFAULT_CONFIG['IMAGES_FOLDER']) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if images:
            return os.path.join(DEFAULT_CONFIG['IMAGES_FOLDER'], random.choice(images))
    return 'https://images.unsplash.com/photo-1530631673369-bc20fdb32288?q=80&w=1760&auto=format&fit=crop'

def generate_ai_message(theme):
    """Génère un message via l'API OpenAI"""
    if not DEFAULT_CONFIG['OPENAI_API_KEY']:
        logger.error("Clé API OpenAI manquante.")
        return None

    client = OpenAI(api_key=DEFAULT_CONFIG['OPENAI_API_KEY'])

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un expert en copywriting et en marketing digital. Génère un message court, percutant et ultra engageant pour une publication Facebook qui promeut un bot Telegram de pronostics football. Le bot donne des coupons avec une forte probabilité de reuissite. "
                        "Le message doit obligatoirement :"
                        " - Commencer par un emoji ⚽, 🔥, 💰 ou 🎯"
                        " - Préciser que c'est gratuit"
                        "-éviter de commencer par le mot <<prêt>>"
                        "- Utiliser un ton amical et engageant"
                        "- Intégrer un appel à l'action clair et motivant : « Rejoins », « Clique ici », « Active ton accès », etc."
                        f"- Terminer par le lien du bot ➡️ https://t.me/Hcfa_bot"
                        "- Longueur idéale : entre 150 et 300 caractères"
                        "- PAS d'explications ni de commentaires, juste le message à publier"
                        f"- Thème spécifique à intégrer: {theme}"
                        "Génère uniquement le message prêt à publier."
                    )
                }
            ],
            max_tokens=300,
            temperature=0.7
        )
        message = response.choices[0].message.content.strip()
        logger.info(f"Message généré: {message}")
        return message
    except Exception as e:
        logger.error(f"Erreur OpenAI: {e}")
        return None

def post_to_facebook(user_id, message, image_path):
    """Publie un message avec une image sur Facebook"""
    if str(user_id) not in USER_CONFIGS:
        logger.error(f"Configuration utilisateur non trouvée pour: {user_id}")
        return None, None
    
    user_config = USER_CONFIGS[str(user_id)]
    
    url = f"{FACEBOOK_GRAPH_URL}/{user_config['PAGE_ID']}/photos"
    payload = {
        'message': message,
        'access_token': user_config['PAGE_ACCESS_TOKEN'],
    }

    try:
        if image_path.startswith("http"):
            payload['url'] = image_path
            files = None
        else:
            files = {'source': open(image_path, 'rb')}

        response = requests.post(url, data=payload, files=files)

        if response.status_code == 200:
            post_id = response.json().get('id')
            logger.info(f"Publication réussie pour l'utilisateur {user_id}. ID: {post_id}")
            save_post_to_csv(user_id, post_id, message, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            return post_id, message
        else:
            logger.error(f"Échec de la publication pour l'utilisateur {user_id}: {response.text}")
            return None, None
    except Exception as e:
        logger.error(f"Erreur lors de la publication pour l'utilisateur {user_id}: {e}")
        return None, None

async def check_expired_tokens(context):
    """Vérifie les tokens qui vont expirer et envoie des alertes"""
    today = datetime.datetime.now().date()
    
    with open(DEFAULT_CONFIG['USERS_CSV'], 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if not row['token_expiry']:
                continue
                
            expiry_date = datetime.datetime.strptime(row['token_expiry'], '%Y-%m-%d').date()
            days_left = (expiry_date - today).days
            
            # Alerte si le token expire dans 2 jours ou moins
            if 0 <= days_left <= 2:
                telegram_id = row['telegram_id']
                # Alerter l'administrateur
                if DEFAULT_CONFIG['ADMIN_TELEGRAM_ID']:
                    await context.bot.send_message(
                        chat_id=DEFAULT_CONFIG['ADMIN_TELEGRAM_ID'],
                        text=f"⚠️ ALERTE: Le token Facebook pour l'utilisateur {telegram_id} (page: {row['page_name']}) expire dans {days_left} jour(s)."
                    )
                
                # Alerter l'utilisateur
                auth_url = get_facebook_auth_url(telegram_id)
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=f"⚠️ Votre accès à Facebook expire dans {days_left} jour(s). Veuillez vous reconnecter pour continuer à utiliser le service.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Reconnecter Facebook", url=auth_url)]
                    ])
                )
                
                logger.info(f"Alerte d'expiration envoyée pour l'utilisateur {telegram_id}")

async def auto_post_job(context):
    """Fonction de publication automatique périodique"""
    user_id = context.job.data
    
    try:
        # Vérifier si l'utilisateur existe
        if str(user_id) not in USER_CONFIGS:
            logger.error(f"Configuration utilisateur non trouvée pour auto-publication: {user_id}")
            return
            
        user_config = USER_CONFIGS[str(user_id)]
        
        # Générer et publier
        message = generate_ai_message(user_config['THEME'])
        if message:
            image = get_random_image()
            post_id, content = post_to_facebook(user_id, message, image)
            
            if post_id:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Publication automatique réussie:\n\n{content}"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Échec de la publication automatique."
                )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ Impossible de générer un message."
            )
    except Exception as e:
        logger.error(f"Erreur dans auto_post_job: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Erreur lors de la publication automatique: {e}"
        )

# États pour le processus de connexion Facebook
AUTH_WAITING_CODE, SELECT_PAGE = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande de démarrage"""
    user_id = str(update.effective_user.id)
    user_is_authenticated = user_id in USER_CONFIGS and USER_CONFIGS[user_id]['PAGE_ACCESS_TOKEN']
    
    keyboard = []
    
    if user_is_authenticated:
        # L'utilisateur est déjà authentifié
        keyboard = [
            [
                InlineKeyboardButton("📊 Statut", callback_data="status"),
                InlineKeyboardButton("🔄 Publier maintenant", callback_data="post_now")
            ],
            [
                InlineKeyboardButton("▶️ Démarrer auto", callback_data="start_auto"),
                InlineKeyboardButton("⏹️ Arrêter auto", callback_data="stop_auto")
            ],
            [
                InlineKeyboardButton("🔧 Paramètres", callback_data="settings")
            ]
        ]
        message = "👋 Bienvenue sur le bot de publications automatiques Facebook!\n\nUtilisez les boutons ci-dessous pour contrôler les publications:"
    else:
        # L'utilisateur doit se connecter à Facebook
        auth_url = get_facebook_auth_url(user_id)
        keyboard = [
            [InlineKeyboardButton("🔑 Se connecter à Facebook", url=auth_url)]
        ]
        message = "👋 Bienvenue sur le bot de publications automatiques Facebook!\n\nPour commencer, vous devez connecter votre compte Facebook afin que nous puissions publier sur vos pages."
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion des boutons interactifs"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Vérifier si l'utilisateur est authentifié
    if query.data != "back_to_menu" and user_id not in USER_CONFIGS:
        auth_url = get_facebook_auth_url(user_id)
        await query.edit_message_text(
            text="❌ Vous devez d'abord vous connecter à Facebook.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Se connecter à Facebook", url=auth_url)]
            ])
        )
        return
    
    if query.data == "status":
        user_data = USER_CONFIGS[user_id]
        token_expiry = "Non défini"
        
        if 'TOKEN_EXPIRY' in user_data and user_data['TOKEN_EXPIRY']:
            expiry_date = datetime.datetime.strptime(user_data['TOKEN_EXPIRY'], '%Y-%m-%d').date()
            today = datetime.datetime.now().date()
            days_left = (expiry_date - today).days
            token_expiry = f"{user_data['TOKEN_EXPIRY']} ({days_left} jours restants)"
        
        status_text = (
            f"📊 *Statut du Bot*\n\n"
            f"• Page Facebook: `{user_data.get('PAGE_NAME', 'Non définie')}`\n"
            f"• Thème actuel: `{user_data.get('THEME', DEFAULT_CONFIG['THEME'])}`\n"
            f"• Intervalle: `{user_data.get('INTERVAL_MINUTES', DEFAULT_CONFIG['INTERVAL_MINUTES'])} minutes`\n"
            f"• Auto-publication: `{'Activée' if user_data.get('AUTO_POST_ENABLED', False) else 'Désactivée'}`\n\n"
            f"*Connexion Facebook:*\n"
            f"• Token expire le: `{token_expiry}`\n"
            f"• API OpenAI: `{'✅ Configuré' if DEFAULT_CONFIG['OPENAI_API_KEY'] else '❌ Non configuré'}`"
        )
        
        await query.edit_message_text(
            text=status_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ Retour au menu", callback_data="back_to_menu")]
            ])
        )
    
    elif query.data == "post_now":
        await query.edit_message_text(
            text="🔄 Génération et publication en cours...",
            reply_markup=None
        )
        
        # Vérifier la configuration de l'utilisateur
        if not USER_CONFIGS[user_id]['PAGE_ACCESS_TOKEN'] or not USER_CONFIGS[user_id]['PAGE_ID']:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Configuration incomplète. Veuillez vous connecter à Facebook."
            )
            await start(update, context)
            return
        
        # Générer et publier
        message = generate_ai_message(USER_CONFIGS[user_id]['THEME'])
        if message:
            image = get_random_image()
            post_id, content = post_to_facebook(user_id, message, image)
            
            if post_id:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"✅ Publication réussie:\n\n{content}"
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Échec de la publication."
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Impossible de générer un message."
            )
            
        # Revenir au menu principal
        await start(update, context)
    
    elif query.data == "start_auto":
        # Vérifier la configuration de l'utilisateur
        if not USER_CONFIGS[user_id]['PAGE_ACCESS_TOKEN'] or not USER_CONFIGS[user_id]['PAGE_ID']:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Configuration incomplète. Veuillez vous connecter à Facebook."
            )
            await start(update, context)
            return
        
        # Vérifier si le job_queue est disponible
        if context.job_queue is None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Erreur: JobQueue n'est pas disponible. Veuillez installer le module job-queue."
            )
            await start(update, context)
            return
        
        # Arrêter d'abord tout job existant pour cet utilisateur
        for job in context.job_queue.get_jobs_by_name(f"auto_post_{user_id}"):
            job.schedule_removal()
        
        # Démarrer le nouveau job
        context.job_queue.run_repeating(
            auto_post_job,
            interval=USER_CONFIGS[user_id]['INTERVAL_MINUTES'] * 60,
            first=10,  # Premier post après 10 secondes
            data=update.effective_chat.id,
            name=f"auto_post_{user_id}"
        )
        
        # Mettre à jour la configuration
        update_user_config(user_id, 'AUTO_POST_ENABLED', True)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Auto-publication activée!\nFréquence: toutes les {USER_CONFIGS[user_id]['INTERVAL_MINUTES']} minutes\nThème: {USER_CONFIGS[user_id]['THEME']}"
        )
        
        # Revenir au menu principal
        await start(update, context)
    
    elif query.data == "stop_auto":
        # Vérifier si le job_queue est disponible
        if context.job_queue is None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Erreur: JobQueue n'est pas disponible."
            )
            await start(update, context)
            return
        
        # Arrêter les jobs existants pour cet utilisateur
        for job in context.job_queue.get_jobs_by_name(f"auto_post_{user_id}"):
            job.schedule_removal()
        
        # Mettre à jour la configuration
        update_user_config(user_id, 'AUTO_POST_ENABLED', False)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏹️ Auto-publication désactivée!"
        )
        
        # Revenir au menu principal
        await start(update, context)
    
    elif query.data == "settings":
        keyboard = [
            [
                InlineKeyboardButton("🏷️ Changer le thème", callback_data="change_theme"),
                InlineKeyboardButton("⏱️ Modifier l'intervalle", callback_data="change_interval")
            ],
            [
                InlineKeyboardButton("🔑 Reconnecter Facebook", 
                                    url=get_facebook_auth_url(user_id))
            ],
            [
                InlineKeyboardButton("↩️ Retour au menu", callback_data="back_to_menu")
            ]
        ]
        
        await query.edit_message_text(
            text="⚙️ *Paramètres*\n\nChoisissez l'option à configurer:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "change_theme":
        # Lancer la conversation pour changer le thème
        context.user_data['prev_message_id'] = query.message.message_id
        await query.edit_message_text(
            text="🏷️ *Changer le thème de publications*\n\nVeuillez entrer le nouveau thème pour vos publications:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ Annuler", callback_data="back_to_menu")]
            ])
        )
        return WAITING_FOR_THEME
    
    elif query.data == "change_interval":
        # Lancer la conversation pour changer l'intervalle
        context.user_data['prev_message_id'] = query.message.message_id
        await query.edit_message_text(
            text="⏱️ *Modifier l'intervalle de publication*\n\nVeuillez entrer le nouvel intervalle en minutes (minimum 30):",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ Annuler", callback_data="back_to_menu")]
            ])
        )
        return WAITING_FOR_INTERVAL
    
    elif query.data == "back_to_menu":
        await start(update, context)

async def handle_theme_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'entrée du nouveau thème"""
    user_id = str(update.effective_user.id)
    new_theme = update.message.text.strip()
    
    if len(new_theme) < 3:
        await update.message.reply_text(
            "⚠️ Le thème est trop court. Veuillez entrer au moins 3 caractères."
        )
        return WAITING_FOR_THEME
    
    # Mettre à jour la configuration
    update_user_config(user_id, 'THEME', new_theme)
    
    await update.message.reply_text(f"✅ Thème mis à jour avec succès: *{new_theme}*", parse_mode='Markdown')
    
    # Revenir au menu principal
    await start(update, context)
    return ConversationHandler.END

async def handle_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'entrée du nouvel intervalle"""
    user_id = str(update.effective_user.id)
    
    try:
        new_interval = int(update.message.text.strip())
        
        if new_interval < 30:
            await update.message.reply_text(
                "⚠️ L'intervalle minimum est de 30 minutes. Veuillez entrer une valeur plus élevée."
            )
            return WAITING_FOR_INTERVAL
        
        # Mettre à jour la configuration
        update_user_config(user_id, 'INTERVAL_MINUTES', new_interval)
        
        # Mettre à jour le job en cours si l'auto-publication est activée
        if USER_CONFIGS[user_id]['AUTO_POST_ENABLED'] and context.job_queue:
            for job in context.job_queue.get_jobs_by_name(f"auto_post_{user_id}"):
                job.schedule_removal()
            
            context.job_queue.run_repeating(
                auto_post_job,
                interval=new_interval * 60,
                first=10,
                data=update.effective_chat.id,
                name=f"auto_post_{user_id}"
            )
        
        await update.message.reply_text(f"✅ Intervalle mis à jour avec succès: *{new_interval} minutes*", parse_mode='Markdown')
        
        # Revenir au menu principal
        await start(update, context)
        return ConversationHandler.END
    
    except ValueError:
        await update.message.reply_text(
            "⚠️ Veuillez entrer un nombre valide pour l'intervalle."
        )
        return WAITING_FOR_INTERVAL

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annule et termine la conversation."""
    await update.message.reply_text("❌ Opération annulée.")
    await start(update, context)
    return ConversationHandler.END

async def facebook_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestionnaire pour le webhook de callback Facebook"""
    # Note: Cette fonction devrait être exposée via un webhook ou un serveur Web séparé
    # pour recevoir les redirections de Facebook après l'authentification.
    
    # Dans une implémentation réelle, ce serait un endpoint web séparé
    # Ceci est uniquement à titre d'exemple
    message = update.message.text
    
    # Simuler l'extraction de paramètres d'URL
    if "code=" in message and "state=" in message:
        code = message.split("code=")[1].split("&")[0]
        state = message.split("state=")[1].split("&")[0]
        
        # Le state contient l'ID Telegram
        telegram_id = state
        
        # Échanger le code contre un token
        short_lived_token = exchange_code_for_token(code)
        if not short_lived_token:
            await update.message.reply_text("❌ Erreur lors de l'authentification avec Facebook.")
            return
        
        # Obtenir un token de longue durée
        long_lived_token, expiry_date = get_long_lived_token(short_lived_token)
        if not long_lived_token:
            await update.message.reply_text("❌ Erreur lors de l'obtention du token de longue durée.")
            return
        
        # Récupérer les pages de l'utilisateur
        pages = get_user_pages(long_lived_token)
        if not pages:
            await update.message.reply_text("❌ Erreur lors de la récupération de vos pages Facebook ou aucune page trouvée.")
            return
        
        # Pour simplifier, utiliser automatiquement la première page
        if len(pages) == 1:
            page = pages[0]
            page_id = page['id']
            page_name = page['name']
            page_token = page['access_token']
            
            # Enregistrer les données de l'utilisateur
            save_user_data(telegram_id, page_id, page_name, page_token, expiry_date)
            
            await context.bot.send_message(
                chat_id=telegram_id,
                text=f"✅ Connecté avec succès à la page Facebook: *{page_name}*\n\nVotre configuration est prête!",
                parse_mode='Markdown'
            )
            
            # Envoyer le menu principal
            await context.bot.send_message(
                chat_id=telegram_id,
                text="🔄 Mise à jour du menu principal..."
            )
            
            # Simuler un update pour appeler start
            new_update = Update.de_json({
                'update_id': 0,
                'message': {
                    'message_id': 0,
                    'date': 0,
                    'chat': {'id': telegram_id, 'type': 'private'},
                    'from': {'id': telegram_id, 'is_bot': False, 'first_name': 'User'},
                    'text': '/start'
                }
            }, context.bot)
            
            await start(new_update, context)
        else:
            # Créer des boutons pour chaque page
            keyboard = []
            for page in pages:
                callback_data = f"select_page:{page['id']}:{page['name']}:{long_lived_token}:{expiry_date}"
                # Limiter la longueur du callback_data
                if len(callback_data) > 64:  # Limite Telegram pour callback_data
                    # Simplifier pour rester dans les limites
                    callback_data = f"select_page:{page['id']}"
                    # Stocker les données complètes dans context.user_data
                    if 'page_options' not in context.user_data:
                        context.user_data['page_options'] = {}
                    context.user_data['page_options'][page['id']] = {
                        'name': page['name'],
                        'token': long_lived_token,
                        'expiry': expiry_date
                    }
                
                keyboard.append([InlineKeyboardButton(page['name'], callback_data=callback_data)])
            
            await context.bot.send_message(
                chat_id=telegram_id,
                text="🔍 Veuillez sélectionner la page Facebook à utiliser:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text("❌ Format de callback invalide. Veuillez réessayer l'authentification.")

async def select_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la sélection de page après l'authentification Facebook"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    callback_data = query.data
    
    if callback_data.startswith("select_page:"):
        parts = callback_data.split(":")
        page_id = parts[1]
        
        if len(parts) >= 5:
            # Toutes les données sont dans le callback
            page_name = parts[2]
            long_lived_token = parts[3]
            expiry_date = parts[4]
        else:
            # Récupérer les données du context.user_data
            if 'page_options' in context.user_data and page_id in context.user_data['page_options']:
                page_data = context.user_data['page_options'][page_id]
                page_name = page_data['name']
                long_lived_token = page_data['token']
                expiry_date = page_data['expiry']
            else:
                await query.edit_message_text("❌ Erreur: données de page non trouvées. Veuillez réessayer l'authentification.")
                return
        
        # Enregistrer les données de l'utilisateur
        save_user_data(user_id, page_id, page_name, long_lived_token, expiry_date)
        
        await query.edit_message_text(
            text=f"✅ Page sélectionnée: *{page_name}*\n\nVotre configuration est prête!",
            parse_mode='Markdown'
        )
        
        # Revenir au menu principal
        await start(update, context)

async def daily_token_check(context: ContextTypes.DEFAULT_TYPE):
    """Vérification quotidienne des tokens qui expirent bientôt"""
    await check_expired_tokens(context)

def main():
    """Point d'entrée principal du programme"""
    # Initialiser les fichiers CSV
    initialize_csv_files()
    
    # Charger les données des utilisateurs
    load_users_data()
    
    # Créer l'application
    application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
    
    # Ajouter les handlers de conversation
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler)
        ],
        states={
            WAITING_FOR_THEME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_input)],
            WAITING_FOR_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_interval_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Ajouter d'autres handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(select_page_handler, pattern="^select_page:"))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Handler pour les messages avec un code FB (simulation de callback)
    application.add_handler(MessageHandler(filters.Regex("code="), facebook_callback_handler))
    
    # Vérification quotidienne des tokens
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(
            daily_token_check,
            time=datetime.time(hour=9, minute=0, second=0),  # Vérification quotidienne à 9h00
            days=tuple(range(7))  # Tous les jours de la semaine
        )
    
    # Restaurer les tâches programmées pour les utilisateurs qui avaient activé l'auto-publication
    for user_id, config in USER_CONFIGS.items():
        if config.get('AUTO_POST_ENABLED', False):
            job_queue.run_repeating(
                auto_post_job,
                interval=config['INTERVAL_MINUTES'] * 60,
                first=60,  # Premier post après 1 minute au démarrage
                data=user_id,
                name=f"auto_post_{user_id}"
            )
            logger.info(f"Tâche programmée restaurée pour l'utilisateur {user_id}")
    
    # Démarrer le bot
    application.run_polling()

if __name__ == '__main__':
    main()