import telebot
import requests
import subprocess
import os
import uuid
import json
import mysql.connector
import logging
from html import escape
from logging.handlers import RotatingFileHandler
from datetime import UTC, datetime
from google.cloud import speech_v1p1beta1 as speech
from pydub import AudioSegment

# Configura il logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Formattazione per il logger
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Crea un handler di rotazione che scrive nei log con un massimo di 10MB per file e mantiene fino a 5 file di backup.
rotating_handler = RotatingFileHandler('app.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
rotating_handler.setFormatter(formatter)

# Crea un handler per la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Aggiungi entrambi gli handler al logger
logger.addHandler(rotating_handler)
logger.addHandler(console_handler)

languages = {
    "English": "en",
    "Italiano": "it",
    "Français": "fr",
    "Español": "es",
    "Deutsch": "de"
}

SPEECH_LANGUAGE_CODES = {
    "en": "en-US",
    "it": "it-IT",
    "fr": "fr-FR",
    "es": "es-ES",
    "de": "de-DE",
}
MONTHLY_LIMIT_SECONDS = 10 * 60

USAGE_TEXTS = {
    "it": {
        "remaining": "Tempo rimanente questo mese: {remaining} su 00:10:00.",
        "limit_reached": "Hai esaurito i 10 minuti mensili. Riprova il mese prossimo.",
        "audio_too_long": "Questo audio supera il tempo rimanente del mese. Ti restano {remaining}.",
        "unlimited": "Uso illimitato. Consumo mese corrente: {used}.",
        "first_time_notice": "You can use this bot for up to 10 minutes per month. Send /usage anytime to check your remaining time.",
    },
    "en": {
        "remaining": "Remaining time this month: {remaining} out of 00:10:00.",
        "limit_reached": "You have used all 10 monthly minutes. Please try again next month.",
        "audio_too_long": "This audio is longer than your remaining monthly time. You still have {remaining}.",
        "unlimited": "Unlimited access. Current month usage: {used}.",
        "first_time_notice": "You can use this bot for up to 10 minutes per month. Send /usage anytime to check your remaining time.",
    },
    "fr": {
        "remaining": "Temps restant ce mois-ci : {remaining} sur 00:10:00.",
        "limit_reached": "Vous avez epuise vos 10 minutes mensuelles. Reessayez le mois prochain.",
        "audio_too_long": "Cet audio depasse votre temps mensuel restant. Il vous reste {remaining}.",
        "unlimited": "Utilisation illimitee. Consommation du mois en cours : {used}.",
        "first_time_notice": "You can use this bot for up to 10 minutes per month. Send /usage anytime to check your remaining time.",
    },
    "de": {
        "remaining": "Verbleibende Zeit in diesem Monat: {remaining} von 00:10:00.",
        "limit_reached": "Du hast deine 10 Monatsminuten aufgebraucht. Bitte versuche es naechsten Monat erneut.",
        "audio_too_long": "Diese Audiodatei ist laenger als deine verbleibende Monatszeit. Verbleibend: {remaining}.",
        "unlimited": "Unbegrenzte Nutzung. Verbrauch im aktuellen Monat: {used}.",
        "first_time_notice": "You can use this bot for up to 10 minutes per month. Send /usage anytime to check your remaining time.",
    },
    "es": {
        "remaining": "Tiempo restante este mes: {remaining} de 00:10:00.",
        "limit_reached": "Has agotado tus 10 minutos mensuales. Intentalo de nuevo el mes que viene.",
        "audio_too_long": "Este audio supera tu tiempo mensual restante. Te quedan {remaining}.",
        "unlimited": "Uso ilimitado. Consumo del mes actual: {used}.",
        "first_time_notice": "You can use this bot for up to 10 minutes per month. Send /usage anytime to check your remaining time.",
    },
}

try:
    with open('languages.json', 'r') as lang_file:
        lang_resources = json.load(lang_file)
        phrases = lang_resources['phrases']
except Exception as e:
    logger.error("Error reading languages.json: %s", e)

with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    db_config = config['db_config']


def normalize_chat_ids(values):
    normalized = set()
    for value in values or []:
        try:
            normalized.add(int(value))
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid chat ID in config: %r", value)
    return normalized


ADMIN_CHAT_ID = int(config.get("admin_chat_id", 0) or 0)
UNLIMITED_CHAT_IDS = normalize_chat_ids(config.get("unlimited_chat_ids", []))
if ADMIN_CHAT_ID:
    UNLIMITED_CHAT_IDS.add(ADMIN_CHAT_ID)

bot_token = config['bot_token'] 
bot = telebot.TeleBot(bot_token)

# Client Google Speech-to-Text
client_google = speech.SpeechClient.from_service_account_file(config['google_credentials_file'])

try:
    bot_info = bot.get_me()
    logger.debug("%s %s", "Bot connected with id: ", bot_info.id)
except Exception as e:
    logger.error("%s %s", "Bot connection error: ", e)

def get_language_from_db(chat_id):
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute("SELECT language FROM users WHERE chat_id = %s", (chat_id,))
    lang = cursor.fetchone()
    cursor.close()
    cnx.close()
    return lang[0] if lang else "en"  

def store_language_in_db(chat_id, lang, username=None):
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute(
        "INSERT INTO users (chat_id, language, total_minutes, monthly_month, username) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE language = VALUES(language), username = COALESCE(VALUES(username), username)",
        (chat_id, lang, 0, get_current_month(), username),
    )
    cnx.commit()
    cursor.close()
    cnx.close()

def insert_interaction_into_db(chat_id, duration_seconds=None, username_snapshot=None, content_type=None, status="success"):
    logger.info("%s %s", "ChatID: ", chat_id)
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    rounded_duration = round(duration_seconds, 2) if duration_seconds is not None else None
    cursor.execute(
        "INSERT INTO interactions (ChatID, username_snapshot, content_type, status, duration_seconds) "
        "VALUES (%s, %s, %s, %s, %s)",
        (chat_id, username_snapshot, content_type, status, rounded_duration),
    )
    cnx.commit()
    cursor.close()
    cnx.close()

def get_current_month():
    return datetime.now(UTC).strftime("%Y-%m")


def get_previous_months(count):
    current_month = get_current_month()
    year, month = map(int, current_month.split("-"))
    months_back = []
    for i in range(1, count + 1):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        months_back.append(f"{y:04d}-{m:02d}")
    return months_back


def is_admin(chat_id):
    return chat_id == ADMIN_CHAT_ID


def is_unlimited_user(chat_id):
    return chat_id in UNLIMITED_CHAT_IDS


def get_speech_language_code(language):
    return SPEECH_LANGUAGE_CODES.get(language, "en-US")


def format_seconds_to_hms(seconds):
    total_seconds = max(0, int(round(seconds)))
    hours = total_seconds // 3600
    minutes_part = (total_seconds % 3600) // 60
    seconds_part = total_seconds % 60
    return f"{hours:02d}:{minutes_part:02d}:{seconds_part:02d}"


def format_minutes_to_hms(minutes):
    total_seconds = int(round(minutes * 60))
    hours = total_seconds // 3600
    minutes_part = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes_part:02d}:{seconds:02d}"


def truncate_text(text, max_length):
    value = str(text or "-")
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + "…"


def html_pre(lines):
    return f"<pre>{escape(chr(10).join(lines))}</pre>"


def build_usage_card(title, rows, subtitle=None):
    body_lines = []
    if subtitle:
        body_lines.append(subtitle)
        body_lines.append("")
    label_width = max(len(label) for label, _ in rows)
    for label, value in rows:
        body_lines.append(f"{label:<{label_width}}  {value}")
    return f"<b>{escape(title)}</b>\n{html_pre(body_lines)}"


def get_message_identity(message):
    if getattr(message, "from_user", None):
        if message.from_user.username:
            return f"@{message.from_user.username}"
        full_name = " ".join(
            part for part in [message.from_user.first_name, message.from_user.last_name] if part
        ).strip()
        if full_name:
            return full_name
    if getattr(message, "chat", None):
        if getattr(message.chat, "username", None):
            return f"@{message.chat.username}"
        if getattr(message.chat, "title", None):
            return message.chat.title
    return None


def get_usage_text(lang, key, **kwargs):
    messages = USAGE_TEXTS.get(lang, USAGE_TEXTS["en"])
    template = messages.get(key, USAGE_TEXTS["en"][key])
    return template.format(**kwargs)


def ensure_user_record(chat_id, username=None, preferred_language="en"):
    current_month = get_current_month()
    created = False
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute(
        "SELECT language, total_minutes, monthly_month, username FROM users WHERE chat_id = %s",
        (chat_id,),
    )
    row = cursor.fetchone()

    if row is None:
        language = preferred_language or "en"
        total_minutes = 0.0
        created = True
        cursor.execute(
            "INSERT INTO users (chat_id, language, total_minutes, monthly_month, username) "
            "VALUES (%s, %s, %s, %s, %s)",
            (chat_id, language, total_minutes, current_month, username),
        )
        cnx.commit()
        stored_username = username
    else:
        language, total_minutes, monthly_month, stored_username = row
        updates = []
        params = []

        if monthly_month != current_month:
            total_minutes = 0.0
            updates.append("total_minutes = %s")
            params.append(total_minutes)
            updates.append("monthly_month = %s")
            params.append(current_month)

        if username and username != stored_username:
            stored_username = username
            updates.append("username = %s")
            params.append(username)

        if updates:
            params.append(chat_id)
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE chat_id = %s",
                tuple(params),
            )
            cnx.commit()

    cursor.close()
    cnx.close()

    return {
        "chat_id": chat_id,
        "language": language if row is None else row[0],
        "total_minutes": float(total_minutes or 0.0),
        "monthly_month": current_month,
        "username": stored_username,
        "created": created,
    }


def maybe_send_first_time_notice(message, user_state):
    if user_state.get("created") and not is_unlimited_user(message.chat.id):
        bot.reply_to(message, get_usage_text("en", "first_time_notice"))


def mark_failed_interaction(chat_id, username, content_type, duration_seconds=None):
    insert_interaction_into_db(
        chat_id,
        duration_seconds=duration_seconds,
        username_snapshot=username,
        content_type=content_type,
        status="failed",
    )


def get_user_monthly_usage_seconds(chat_id, username=None):
    state = ensure_user_record(
        chat_id,
        username=username,
        preferred_language=get_language_from_db(chat_id),
    )
    return int(round(float(state["total_minutes"]) * 60))


def get_remaining_monthly_seconds(chat_id, username=None):
    used_seconds = get_user_monthly_usage_seconds(chat_id, username=username)
    return max(0, MONTHLY_LIMIT_SECONDS - used_seconds)


def cleanup_temp_files(*paths):
    for path in paths:
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def update_usage_in_db(chat_id, minutes, username=None):
    user_state = ensure_user_record(
        chat_id,
        username=username,
        preferred_language=get_language_from_db(chat_id),
    )
    current_month = user_state["monthly_month"]
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()

    cursor.execute("UPDATE users SET total_minutes = COALESCE(total_minutes, 0) + %s WHERE chat_id = %s", (minutes, chat_id))
    cursor.execute(
        "INSERT INTO monthly_usage (chat_id, `year_month`, minutes, updated_at) VALUES (%s, %s, %s, NOW()) "
        "ON DUPLICATE KEY UPDATE minutes = minutes + %s, updated_at = NOW()",
        (chat_id, current_month, minutes, minutes)
    )
    cnx.commit()
    cursor.close()
    cnx.close()
    logger.info(f"Aggiornati {minutes} minuti per utente {chat_id}")


def load_language_resources(lang):
    global phrases, welcome_message, help_message, recognition_started, transcription_error
    global operation_cancelled, language_choice, language_error, select_lang, wrong_file_type

    try:
        with open('languages.json', 'r') as lang_file:
            lang_resources = json.load(lang_file)
            phrases = lang_resources['phrases']
            welcome_message = lang_resources[lang]['welcome_message']
            help_message = lang_resources[lang]['help_message']
            recognition_started = lang_resources[lang]['recognition_started']
            transcription_error = lang_resources[lang]['transcription_error']
            operation_cancelled= lang_resources[lang]['operation_cancelled']
            language_choice = lang_resources[lang]['language_choice']
            language_error = lang_resources[lang]['language_error']
            select_lang = lang_resources[lang]['select_lang']       
            wrong_file_type = lang_resources[lang]['wrong_file_type']        
    except Exception as e:
        logger.error("Error reading languages.json: %s", e)


def remove_phrases(text):
    for phrase in phrases:
        text = text.replace(phrase, "")
    return text

def set_language(message):
    chat_id = message.chat.id
    lang_choice = message.text

    if lang_choice in languages:
        language = languages[lang_choice]
        store_language_in_db(chat_id, language, username=get_message_identity(message))
        load_language_resources(language)
        markup = telebot.types.ReplyKeyboardRemove()
        bot.send_message(chat_id, f"{language_choice} {lang_choice}!", reply_markup=markup)
    else:
        bot.send_message(chat_id, language_error)
        send_language_keyboard(chat_id)

def send_language_keyboard(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for lang in languages:
        markup.add(lang)

    bot.send_message(chat_id, select_lang, reply_markup=markup)
    bot.register_next_step_handler_by_chat_id(chat_id, set_language)

# Definizione della funzione split_message
def split_message(message, size=4096):
    words = message.split()
    if not words:
        return [""]
    chunks = []
    current_chunk = words[0]

    for word in words[1:]:
        if len(current_chunk) + len(word) + 1 <= size:
            current_chunk += " " + word
        else:
            chunks.append(current_chunk)
            current_chunk = word

    chunks.append(current_chunk)
    return chunks  

@bot.message_handler(commands=["help"])
def send_help(message):
    chat_id = message.chat.id
    user_state = ensure_user_record(chat_id, username=get_message_identity(message), preferred_language=get_language_from_db(chat_id))
    maybe_send_first_time_notice(message, user_state)
    current_language = user_state["language"]
    load_language_resources(current_language)   
    bot.reply_to(
        message, help_message,
    )
@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    user_state = ensure_user_record(chat_id, username=get_message_identity(message), preferred_language=get_language_from_db(chat_id))
    maybe_send_first_time_notice(message, user_state)
    current_language = user_state["language"]
    load_language_resources(current_language)
    bot.reply_to(message, welcome_message)

@bot.message_handler(commands=["usage"])
def usage_command(message):
    logger.info(f"Comando /usage ricevuto da {message.chat.id}")
    chat_id = message.chat.id
    username = get_message_identity(message)
    user_state = ensure_user_record(chat_id, username=username, preferred_language=get_language_from_db(chat_id))
    maybe_send_first_time_notice(message, user_state)
    current_language = user_state["language"]
    load_language_resources(current_language)

    if is_admin(chat_id):
        bot.reply_to(message, build_admin_usage_report_html(), parse_mode="HTML")
        return

    used_seconds = int(round(float(user_state["total_minutes"]) * 60))
    if is_unlimited_user(chat_id):
        usage_html = build_usage_card(
            "Usage",
            [
                ("Access", "Unlimited"),
                ("Used This Month", format_seconds_to_hms(used_seconds)),
            ],
            subtitle=get_usage_text(
                current_language,
                "unlimited",
                used=format_seconds_to_hms(used_seconds),
            ),
        )
        bot.reply_to(message, usage_html, parse_mode="HTML")
        return

    remaining_seconds = max(0, MONTHLY_LIMIT_SECONDS - used_seconds)
    if remaining_seconds <= 0:
        usage_html = build_usage_card(
            "Usage",
            [
                ("Plan", "Monthly"),
                ("Used This Month", format_seconds_to_hms(used_seconds)),
                ("Remaining", "00:00:00"),
                ("Limit", format_seconds_to_hms(MONTHLY_LIMIT_SECONDS)),
            ],
            subtitle=get_usage_text(current_language, "limit_reached"),
        )
        bot.reply_to(message, usage_html, parse_mode="HTML")
        return

    usage_html = build_usage_card(
        "Usage",
        [
            ("Plan", "Monthly"),
            ("Used This Month", format_seconds_to_hms(used_seconds)),
            ("Remaining", format_seconds_to_hms(remaining_seconds)),
            ("Limit", format_seconds_to_hms(MONTHLY_LIMIT_SECONDS)),
        ],
        subtitle=get_usage_text(
            current_language,
            "remaining",
            remaining=format_seconds_to_hms(remaining_seconds),
        ),
    )
    bot.reply_to(message, usage_html, parse_mode="HTML")

@bot.message_handler(commands=["changelanguage"])
def change_language_command(message):
    chat_id = message.chat.id
    user_state = ensure_user_record(chat_id, username=get_message_identity(message), preferred_language=get_language_from_db(chat_id))
    maybe_send_first_time_notice(message, user_state)
    current_language = user_state["language"]
    load_language_resources(current_language)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for lang_name in languages:
        markup.add(telebot.types.KeyboardButton(lang_name))
    bot.send_message(message.chat.id, select_lang, reply_markup=markup)
    bot.register_next_step_handler(message, set_language)


def build_admin_usage_report_html():
    current_month = get_current_month()
    previous_months = get_previous_months(12)

    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute(
        "SELECT i.ChatID, i.username_snapshot "
        "FROM interactions i "
        "INNER JOIN ("
        "    SELECT ChatID, MAX(ID) AS max_id "
        "    FROM interactions "
        "    WHERE username_snapshot IS NOT NULL "
        "    GROUP BY ChatID"
        ") latest ON latest.max_id = i.ID"
    )
    username_snapshots = {row_chat_id: row_username for row_chat_id, row_username in cursor.fetchall()}

    cursor.execute(
        "SELECT chat_id, username, COALESCE(total_minutes, 0) "
        "FROM users WHERE monthly_month = %s ORDER BY COALESCE(total_minutes, 0) DESC, chat_id",
        (current_month,),
    )
    user_rows = cursor.fetchall()

    cursor.execute(
        "SELECT COALESCE(SUM(duration_seconds), 0) FROM interactions "
        "WHERE status = 'success' AND Date >= CURDATE() AND Date < CURDATE() + INTERVAL 1 DAY"
    )
    daily_total_seconds = float(cursor.fetchone()[0] or 0)

    cursor.execute(
        "SELECT status, COUNT(*) "
        "FROM interactions "
        "WHERE Date >= CURDATE() AND Date < CURDATE() + INTERVAL 1 DAY "
        "GROUP BY status"
    )
    daily_status_counts = {status: int(count) for status, count in cursor.fetchall()}

    cursor.execute(
        "SELECT ChatID, COALESCE(username_snapshot, ''), COUNT(*) "
        "FROM interactions "
        "WHERE status = 'failed' AND Date >= CURDATE() AND Date < CURDATE() + INTERVAL 1 DAY "
        "GROUP BY ChatID, username_snapshot "
        "ORDER BY COUNT(*) DESC, ChatID"
    )
    failed_rows = cursor.fetchall()

    cursor.execute(
        "SELECT COALESCE(content_type, 'unknown'), status, COUNT(*) "
        "FROM interactions "
        "WHERE Date >= CURDATE() AND Date < CURDATE() + INTERVAL 1 DAY "
        "GROUP BY COALESCE(content_type, 'unknown'), status "
        "ORDER BY COALESCE(content_type, 'unknown'), status"
    )
    content_type_rows = cursor.fetchall()

    cursor.execute(
        "SELECT COALESCE(SUM(total_minutes), 0) FROM users WHERE monthly_month = %s",
        (current_month,),
    )
    monthly_total_seconds = float(cursor.fetchone()[0] or 0) * 60

    previous_total_seconds = 0.0
    if previous_months:
        placeholders = ", ".join(["%s"] * len(previous_months))
        cursor.execute(
            f"SELECT COALESCE(SUM(minutes), 0) FROM monthly_usage WHERE `year_month` IN ({placeholders})",
            tuple(previous_months),
        )
        previous_total_seconds = float(cursor.fetchone()[0] or 0) * 60

    cursor.close()
    cnx.close()

    content_type_summary = {}
    for content_type, status, count in content_type_rows:
        stats = content_type_summary.setdefault(content_type, {"success": 0, "failed": 0})
        stats[status] = int(count)

    report_lines = [
        f"MONTH  {current_month}",
        "=" * 52,
        "",
        "CURRENT MONTH BY USER",
        f"{'CHAT ID':<14} {'USERNAME':<18} {'USED':>8}",
        f"{'-' * 14} {'-' * 18} {'-' * 8}",
    ]
    for row_chat_id, row_username, total_minutes in user_rows:
        label = row_username or username_snapshots.get(row_chat_id) or "-"
        seconds_used = int(round(float(total_minutes or 0) * 60))
        report_lines.append(
            f"{str(row_chat_id):<14} {truncate_text(label, 18):<18} {format_seconds_to_hms(seconds_used):>8}"
        )

    report_lines.extend(
        [
            "",
            "OVERVIEW",
            f"{'Today success':<18} {format_seconds_to_hms(daily_total_seconds)}",
            f"{'Today attempts':<18} {daily_status_counts.get('success', 0)} ok / {daily_status_counts.get('failed', 0)} fail",
            f"{'Current month':<18} {format_seconds_to_hms(monthly_total_seconds)}",
            f"{'Prev. 12 months':<18} {format_seconds_to_hms(previous_total_seconds)}",
            "",
            "FAILURES TODAY",
        ]
    )

    if failed_rows:
        report_lines.append(f"{'CHAT ID':<14} {'USERNAME':<18} {'FAILS':>5}")
        report_lines.append(f"{'-' * 14} {'-' * 18} {'-' * 5}")
        for failed_chat_id, failed_username, failed_count in failed_rows:
            label = failed_username or username_snapshots.get(failed_chat_id) or "-"
            report_lines.append(
                f"{str(failed_chat_id):<14} {truncate_text(label, 18):<18} {str(failed_count):>5}"
            )
    else:
        report_lines.append("No failures today.")

    report_lines.extend(
        [
            "",
            "CONTENT TODAY",
            f"{'TYPE':<10} {'OK':>5} {'FAIL':>5}",
        ]
    )
    if content_type_summary:
        report_lines.append(f"{'-' * 10} {'-' * 5} {'-' * 5}")
        for content_type in sorted(content_type_summary):
            stats = content_type_summary[content_type]
            report_lines.append(
                f"{truncate_text(content_type, 10):<10} {str(stats.get('success', 0)):>5} {str(stats.get('failed', 0)):>5}"
            )
    else:
        report_lines.append("No interactions today.")

    return "<b>Usage Dashboard</b>\n" f"{html_pre(report_lines)}"


@bot.message_handler(content_types=['voice', 'audio', 'document'])
def handle_media_messages(message):
    chat_id = message.chat.id
    username = get_message_identity(message)
    interaction_content_type = message.content_type
    duration_seconds = None
    user_state = ensure_user_record(chat_id, username=username, preferred_language=get_language_from_db(chat_id))
    maybe_send_first_time_notice(message, user_state)
    current_language = user_state["language"]
    load_language_resources(current_language)
    logger.debug("%s %s", "ChatId: ", chat_id)

    if not is_unlimited_user(chat_id):
        remaining_seconds = max(0, MONTHLY_LIMIT_SECONDS - int(round(float(user_state["total_minutes"]) * 60)))
        if remaining_seconds <= 0:
            mark_failed_interaction(chat_id, username, interaction_content_type)
            bot.reply_to(message, get_usage_text(current_language, "limit_reached"))
            return
    else:
        remaining_seconds = None

    # Determina il tipo di file e ottieni il file_path corrispondente
    try:
        if message.content_type == 'voice':
            file_info = bot.get_file(message.voice.file_id)
        elif message.content_type == 'audio':
            file_info = bot.get_file(message.audio.file_id)
        elif message.content_type == 'document':
            # Verifica se il documento è un file audio per estensione o MIME type
            mime_type = message.document.mime_type or ""
            document_name = (message.document.file_name or "").lower()
            extension = document_name.rsplit('.', 1)[-1] if '.' in document_name else ""
            if mime_type.startswith('audio') or extension in ['mp3', 'wav', 'ogg', 'm4a']:
                file_info = bot.get_file(message.document.file_id)
            else:
                mark_failed_interaction(chat_id, username, interaction_content_type)
                bot.reply_to(message, wrong_file_type)
                return
        else:
            mark_failed_interaction(chat_id, username, interaction_content_type)
            bot.reply_to(message, "Tipo di file non supportato.")
            return
    except Exception as e:
        logger.error("Error getting Telegram file info: %s", e)
        mark_failed_interaction(chat_id, username, interaction_content_type)
        bot.reply_to(message, transcription_error)
        return

    file_path = file_info.file_path
    file_url = f'https://api.telegram.org/file/bot{bot_token}/{file_path}'

    download_started_at = datetime.now(UTC)
    logger.info('Downloading audio file...')
    try:
        audio_file = requests.get(file_url, timeout=30)
        audio_file.raise_for_status()
    except Exception as e:
        logger.error("Error downloading audio file: %s", e)
        mark_failed_interaction(chat_id, username, interaction_content_type)
        bot.reply_to(message, transcription_error)
        return
    logger.info("Download completato in %.3f secondi", (datetime.now(UTC) - download_started_at).total_seconds())

    file_extension = file_path.split('.')[-1]
    file_name = f'{str(uuid.uuid4())}.{file_extension}'
    
    with open(file_name, 'wb') as f:
        f.write(audio_file.content)

    sent_message = bot.reply_to(message, recognition_started, parse_mode='Markdown')
    logger.info('Converting audio file to WAV format...')
    wav_file_name = f'{str(uuid.uuid4())}.wav'
    try:
        conversion_started_at = datetime.now(UTC)
        subprocess.run(
            ['ffmpeg', '-y', '-i', file_name, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', wav_file_name],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Conversione WAV completata in %.3f secondi", (datetime.now(UTC) - conversion_started_at).total_seconds())
    except Exception as e:
        logger.error("Error converting audio file with FFmpeg: %s", e)
        mark_failed_interaction(chat_id, username, interaction_content_type)
        bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error)
        cleanup_temp_files(file_name, wav_file_name)
        return

    transcript = None
    try:
        # Calcola durata dell'audio
        audio = AudioSegment.from_file(wav_file_name)
        duration_seconds = len(audio) / 1000.0
        duration_minutes = duration_seconds / 60.0
        duration_minutes = round(duration_minutes, 4)
        if duration_minutes < 0 or duration_minutes > 1000:  # Limite ragionevole
            duration_minutes = 0
        logger.info(f"Durata audio: {duration_seconds} secondi ({duration_minutes} minuti)")

        if remaining_seconds is not None and duration_seconds > remaining_seconds:
            mark_failed_interaction(chat_id, username, interaction_content_type, duration_seconds=duration_seconds)
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=sent_message.message_id,
                text=get_usage_text(
                    current_language,
                    "audio_too_long",
                    remaining=format_seconds_to_hms(remaining_seconds),
                ),
            )
            cleanup_temp_files(file_name, wav_file_name)
            return

        # Usa Google Speech-to-Text
        with open(wav_file_name, "rb") as audio_file:
            content = audio_file.read()

        recognition_audio = speech.RecognitionAudio(content=content)
        speech_language_code = get_speech_language_code(current_language)
        config_speech = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=speech_language_code,
            enable_automatic_punctuation=True,
        )
        logger.info("Google Speech language code: %s", speech_language_code)

        speech_started_at = datetime.now(UTC)
        if duration_seconds <= 55:
            response = client_google.recognize(config=config_speech, audio=recognition_audio)
            logger.info("Google recognize completato in %.3f secondi", (datetime.now(UTC) - speech_started_at).total_seconds())
        else:
            operation = client_google.long_running_recognize(config=config_speech, audio=recognition_audio)
            response = operation.result(timeout=180)
            logger.info(
                "Google long_running_recognize completato in %.3f secondi",
                (datetime.now(UTC) - speech_started_at).total_seconds(),
            )

        transcript_parts = []
        for result in response.results:
            transcript_parts.append(result.alternatives[0].transcript.strip())

        transcript = " ".join(part for part in transcript_parts if part)

        logger.debug(transcript)
        transcript = remove_phrases(transcript)
        logger.debug(transcript)

        # Salva utilizzo e interazione solo quando l'audio e' stato elaborato correttamente.
        update_usage_in_db(chat_id, duration_minutes, username=username)
        insert_interaction_into_db(
            chat_id,
            duration_seconds=duration_seconds,
            username_snapshot=username,
            content_type=interaction_content_type,
            status="success",
        )

        if transcript is not None and transcript.strip():
            message_parts = split_message(transcript)                
            bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=message_parts[0])
            for part in message_parts[1:]:
                bot.send_message(chat_id=message.chat.id, text=part)                
        else:
            bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error)
    except FileNotFoundError as e:
        logger.error(f"File non trovato: {e}")
        mark_failed_interaction(chat_id, username, interaction_content_type, duration_seconds=duration_seconds)
    except Exception as e:
        logger.error("%s %s", "Error transcribing audio file:", e)
        mark_failed_interaction(chat_id, username, interaction_content_type, duration_seconds=duration_seconds)
        transcription_error_message = f"{transcription_error} {e}"
        bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error_message)

    logger.info('Deleting audio file...')
    cleanup_temp_files(file_name, wav_file_name)

bot.polling()
