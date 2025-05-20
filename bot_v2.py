import os
import time
import random
import csv
import datetime
import requests
import asyncio
import logging
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
    'THEME': os.getenv('THEME','promo du bot MATCH_PREDICTION_AI'),
    'INTERVAL_MINUTES': int(os.getenv('INTERVAL_MINUTES', '60')),
    'PAGE_ACCESS_TOKEN': os.getenv('PAGE_ACCESS_TOKEN', ''),
    'PAGE_ID': os.getenv('PAGE_ID', ''),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
    'IMAGES_FOLDER': 'images',
    'MESSAGES_CSV': 'messages.csv',
    'AUTO_POST_ENABLED': True
}

# Variables globales pour stocker la configuration actuelle
CONFIG = DEFAULT_CONFIG.copy()
posting_task = None

def initialize_csv_file():
    """Initialise le fichier CSV s'il n'existe pas"""
    if not os.path.exists(CONFIG['MESSAGES_CSV']):
        with open(CONFIG['MESSAGES_CSV'], 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['id_post', 'message', 'date_post'])
            writer.writeheader()
            logger.info(f"Fichier CSV '{CONFIG['MESSAGES_CSV']}' créé.")

def save_post_to_csv(post_id, message, date_post):
    """Enregistre un post dans le CSV"""
    with open(CONFIG['MESSAGES_CSV'], 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['id_post', 'message', 'date_post'])
        writer.writerow({'id_post': post_id, 'message': message, 'date_post': date_post})
        logger.info("Post enregistré dans le CSV.")

def get_random_image():
    """Récupère une image aléatoire du dossier ou utilise une URL par défaut"""
    if os.path.exists(CONFIG['IMAGES_FOLDER']):
        images = [f for f in os.listdir(CONFIG['IMAGES_FOLDER']) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if images:
            return os.path.join(CONFIG['IMAGES_FOLDER'], random.choice(images))
    return 'https://images.unsplash.com/photo-1530631673369-bc20fdb32288?q=80&w=1760&auto=format&fit=crop'

def generate_ai_message(theme):
    """Génère un message via l'API OpenAI"""
    if not CONFIG['OPENAI_API_KEY']:
        logger.error("Clé API OpenAI manquante.")
        return None

    client = OpenAI(api_key=CONFIG['OPENAI_API_KEY'])

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

def post_to_facebook(message, image_path):
    """Publie un message avec une image sur Facebook"""
    url = f"https://graph.facebook.com/{CONFIG['PAGE_ID']}/photos"
    payload = {
        'message': message,
        'access_token': CONFIG['PAGE_ACCESS_TOKEN'],
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
            logger.info(f"Publication réussie. ID: {post_id}")
            save_post_to_csv(post_id, message, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            return post_id, message
        else:
            logger.error(f"Échec de la publication: {response.text}")
            return None, None
    except Exception as e:
        logger.error(f"Erreur lors de la publication: {e}")
        return None, None

async def auto_post_job(context):
    """Fonction de publication automatique périodique"""
    chat_id = context.job.data
    
    try:
        # Générer et publier
        message = generate_ai_message(CONFIG['THEME'])
        if message:
            image = get_random_image()
            post_id, content = post_to_facebook(message, image)
            
            if post_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Publication automatique réussie:\n\n{content}"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Échec de la publication automatique."
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Impossible de générer un message."
            )
    except Exception as e:
        logger.error(f"Erreur dans auto_post_job: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Erreur lors de la publication automatique: {e}"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande de démarrage"""
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Bienvenue sur le bot de publications automatiques Facebook!\n\n"
        "Utilisez les boutons ci-dessous pour contrôler les publications:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion des boutons interactifs"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "status":
        status_text = (
            f"📊 *Statut du Bot*\n\n"
            f"• Thème actuel: `{CONFIG['THEME']}`\n"
            f"• Intervalle: `{CONFIG['INTERVAL_MINUTES']} minutes`\n"
            f"• Auto-publication: `{'Activée' if CONFIG['AUTO_POST_ENABLED'] else 'Désactivée'}`\n\n"
            f"*Connexion Facebook:*\n"
            f"• Token: `{'✅ Configuré' if CONFIG['PAGE_ACCESS_TOKEN'] else '❌ Non configuré'}`\n"
            f"• Page ID: `{'✅ Configuré' if CONFIG['PAGE_ID'] else '❌ Non configuré'}`\n"
            f"• API OpenAI: `{'✅ Configuré' if CONFIG['OPENAI_API_KEY'] else '❌ Non configuré'}`"
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
        
        # Vérifier les tokens et l'API
        if not CONFIG['PAGE_ACCESS_TOKEN'] or not CONFIG['PAGE_ID'] or not CONFIG['OPENAI_API_KEY']:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Configuration incomplète. Veuillez vérifier vos paramètres."
            )
            await start(update, context)
            return
        
        # Générer et publier
        message = generate_ai_message(CONFIG['THEME'])
        if message:
            image = get_random_image()
            post_id, content = post_to_facebook(message, image)
            
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
        # Vérifier la configuration
        if not CONFIG['PAGE_ACCESS_TOKEN'] or not CONFIG['PAGE_ID'] or not CONFIG['OPENAI_API_KEY']:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Configuration incomplète. Veuillez vérifier vos paramètres."
            )
            await start(update, context)
            return
        
        # Vérifier si le job_queue est disponible
        if context.job_queue is None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Erreur: JobQueue n'est pas disponible. Veuillez installer le module job-queue avec 'pip install \"python-telegram-bot[job-queue]\"'"
            )
            await start(update, context)
            return
        
        # Arrêter d'abord tout job existant
        for job in context.job_queue.get_jobs_by_name("auto_post"):
            job.schedule_removal()
        
        # Démarrer le nouveau job
        context.job_queue.run_repeating(
            auto_post_job,
            interval=CONFIG['INTERVAL_MINUTES'] * 60,
            first=10,  # Premier post après 10 secondes
            data=update.effective_chat.id,
            name="auto_post"
        )
        
        CONFIG['AUTO_POST_ENABLED'] = True
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Auto-publication activée!\nFréquence: toutes les {CONFIG['INTERVAL_MINUTES']} minutes\nThème: {CONFIG['THEME']}"
        )
        
        # Revenir au menu principal
        await start(update, context)
    
    elif query.data == "stop_auto":
        # Vérifier si le job_queue est disponible
        if context.job_queue is None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Erreur: JobQueue n'est pas disponible. Veuillez installer le module job-queue avec 'pip install \"python-telegram-bot[job-queue]\"'"
            )
            await start(update, context)
            return
        
        # Arrêter les jobs existants
        for job in context.job_queue.get_jobs_by_name("auto_post"):
            job.schedule_removal()
        
        CONFIG['AUTO_POST_ENABLED'] = False
        
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
                InlineKeyboardButton("⏱️ Changer l'intervalle", callback_data="change_interval")
            ],
            [
                InlineKeyboardButton("🔑 Configurer API", callback_data="configure_api"),
                InlineKeyboardButton("📄 Configurer Facebook", callback_data="configure_facebook")
            ],
            [
                InlineKeyboardButton("↩️ Retour au menu", callback_data="back_to_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="🔧 Paramètres du bot:",
            reply_markup=reply_markup
        )
    
    elif query.data == "change_theme":
        await query.edit_message_text(
            text=f"🏷️ Thème actuel: {CONFIG['THEME']}\n\nEnvoyez-moi le nouveau thème:",
            reply_markup=None
        )
        return WAITING_FOR_THEME
    
    elif query.data == "change_interval":
        await query.edit_message_text(
            text=f"⏱️ Intervalle actuel: {CONFIG['INTERVAL_MINUTES']} minutes\n\nEnvoyez-moi le nouvel intervalle (en minutes):",
            reply_markup=None
        )
        return WAITING_FOR_INTERVAL
    
    elif query.data == "configure_api":
        await query.edit_message_text(
            text="🔑 Configuration de l'API OpenAI\n\n"
                 "Pour configurer l'API, envoyez la commande:\n"
                 "/set_openai_key VOTRE_CLÉ_API",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ Retour aux paramètres", callback_data="settings")]
            ])
        )
    
    elif query.data == "configure_facebook":
        await query.edit_message_text(
            text="📄 Configuration de Facebook\n\n"
                 "Pour configurer l'accès à Facebook, envoyez ces commandes:\n\n"
                 "/set_page_token VOTRE_TOKEN_ACCÈS\n"
                 "/set_page_id VOTRE_ID_PAGE",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ Retour aux paramètres", callback_data="settings")]
            ])
        )
    
    elif query.data == "back_to_menu":
        await start(update, context)

async def receive_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit le nouveau thème"""
    new_theme = update.message.text
    CONFIG['THEME'] = new_theme
    
    await update.message.reply_text(
        f"✅ Thème mis à jour: {new_theme}"
    )
    
    # Revenir au menu principal
    await start(update, context)
    return ConversationHandler.END

async def receive_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit le nouvel intervalle"""
    try:
        new_interval = int(update.message.text)
        if new_interval < 1:
            await update.message.reply_text(
                "⚠️ L'intervalle doit être d'au moins 1 minute."
            )
            return WAITING_FOR_INTERVAL
        
        CONFIG['INTERVAL_MINUTES'] = new_interval
        
        # Mettre à jour le job s'il est actif
        if CONFIG['AUTO_POST_ENABLED'] and context.job_queue is not None:
            for job in context.job_queue.get_jobs_by_name("auto_post"):
                job.schedule_removal()
            
            context.job_queue.run_repeating(
                auto_post_job,
                interval=CONFIG['INTERVAL_MINUTES'] * 60,
                first=10,
                data=update.effective_chat.id,
                name="auto_post"
            )
        
        await update.message.reply_text(
            f"✅ Intervalle mis à jour: {new_interval} minutes"
        )
        
        # Revenir au menu principal
        await start(update, context)
        return ConversationHandler.END
    
    except ValueError:
        await update.message.reply_text(
            "⚠️ Veuillez entrer un nombre valide."
        )
        return WAITING_FOR_INTERVAL

async def set_openai_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit la clé API OpenAI"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Syntaxe: /set_openai_key VOTRE_CLÉ_API"
        )
        return
    
    CONFIG['OPENAI_API_KEY'] = context.args[0]
    await update.message.reply_text(
        "✅ Clé API OpenAI mise à jour"
    )
    
    # Supprimer le message pour ne pas exposer la clé
    await update.message.delete()

async def set_page_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit le token d'accès à la page Facebook"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Syntaxe: /set_page_token VOTRE_TOKEN_ACCÈS"
        )
        return
    
    CONFIG['PAGE_ACCESS_TOKEN'] = context.args[0]
    await update.message.reply_text(
        "✅ Token d'accès à la page Facebook mis à jour"
    )
    
    # Supprimer le message pour ne pas exposer le token
    await update.message.delete()

async def set_page_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit l'ID de la page Facebook"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Syntaxe: /set_page_id VOTRE_ID_PAGE"
        )
        return
    
    CONFIG['PAGE_ID'] = context.args[0]
    await update.message.reply_text(
        "✅ ID de la page Facebook mis à jour"
    )

async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définit l'intervalle entre les publications"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Syntaxe: /set_interval MINUTES"
        )
        return
    
    try:
        minutes = int(context.args[0])
        if minutes < 1:
            await update.message.reply_text(
                "⚠️ L'intervalle doit être d'au moins 1 minute."
            )
            return
            
        old_interval = CONFIG['INTERVAL_MINUTES']
        CONFIG['INTERVAL_MINUTES'] = minutes
        
        # Mettre à jour le job s'il est actif
        if CONFIG['AUTO_POST_ENABLED'] and context.job_queue is not None:
            for job in context.job_queue.get_jobs_by_name("auto_post"):
                job.schedule_removal()
            
            context.job_queue.run_repeating(
                auto_post_job,
                interval=CONFIG['INTERVAL_MINUTES'] * 60,
                first=10,
                data=update.effective_chat.id,
                name="auto_post"
            )
        
        await update.message.reply_text(
            f"✅ Intervalle mis à jour: {minutes} minutes (ancienne valeur: {old_interval} minutes)"
        )
    except ValueError:
        await update.message.reply_text(
            "⚠️ Veuillez entrer un nombre valide."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'aide"""
    help_text = (
        "🔍 *Aide du Bot de Publication*\n\n"
        "*Commandes disponibles:*\n"
        "• /start - Démarrer le bot et afficher le menu principal\n"
        "• /help - Afficher cette aide\n"
        "• /set_openai_key VOTRE_CLÉ - Configurer la clé API OpenAI\n"
        "• /set_page_token VOTRE_TOKEN - Configurer le token Facebook\n"
        "• /set_page_id VOTRE_ID - Configurer l'ID de la page Facebook\n"
        "• /set_interval MINUTES - Définir l'intervalle entre les publications\n\n"
        "*Utilisation:*\n"
        "1. Configurez vos paramètres (API et Facebook)\n"
        "2. Démarrez les publications automatiques\n"
        "3. Modifiez le thème et l'intervalle selon vos besoins\n\n"
        "Pour plus d'aide, contactez l'administrateur."
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )

async def error_handler(update, context):
    """Gère les erreurs"""
    logger.error(f"Exception lors du traitement d'une mise à jour: {context.error}")
    
    # Envoyer un message à l'utilisateur
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Une erreur s'est produite: {context.error}"
        )

def main():
    """Fonction principale"""
    # Vérifier si le dossier d'images existe
    if not os.path.exists(CONFIG['IMAGES_FOLDER']):
        os.makedirs(CONFIG['IMAGES_FOLDER'])
        logger.info(f"Dossier images créé : {CONFIG['IMAGES_FOLDER']}")
    
    # Initialiser le fichier CSV
    initialize_csv_file()
    
    # Récupérer le token du bot Telegram
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("Token Telegram manquant. Définissez TELEGRAM_BOT_TOKEN dans le fichier .env")
        return
    
    # Créer l'application avec job_queue
    app = Application.builder().token(token).build()
    
  
    # Gestionnaire de conversation pour les paramètres
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            WAITING_FOR_THEME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_theme)],
            WAITING_FOR_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_interval)],
        },
        fallbacks=[CommandHandler('start', start)],
        per_message=True,  # Correction du warning
    )
    
    # Ajouter les gestionnaires
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('set_openai_key', set_openai_key))
    app.add_handler(CommandHandler('set_page_token', set_page_token))
    app.add_handler(CommandHandler('set_page_id', set_page_id))
    app.add_handler(CommandHandler('set_interval', set_interval))
    app.add_handler(conv_handler)
    
    # Ajouter le gestionnaire d'erreurs
    app.add_error_handler(error_handler)
    
    # Lancer le bot
    logger.info("Bot Telegram démarré")
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Erreur critique: {e}")