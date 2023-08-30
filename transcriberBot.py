import telebot
import requests
import openai
import subprocess
import os
import uuid
import json
import mysql.connector
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(),
                              logging.FileHandler('app.log', encoding='utf-8')])

language = None
current_openai_key = None

languages = {
    "English": "en",
    "Italiano": "it",
    "Français": "fr",
    "Español": "es",
    "Deutsch": "de"
}

logger = logging.getLogger(__name__)
from cryptography.fernet import Fernet

with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    cipher = Fernet(config['encryption_key'])
    db_config = config['db_config']


with open('languages.json') as lang_file:
    lang_resources = json.load(lang_file)    

#openai.api_key = config['openai_api_key']
bot_token = config['bot_token'] 
bot = telebot.TeleBot(bot_token)

try:
    bot_info = bot.get_me()
    logger.debug("%s %s", "Bot connected with id: ", bot_info.id)
except Exception as e:
    logger.error("%s %s", "Bot connection error: ", e)

def encrypt_data(data):
    encrypted_data = cipher.encrypt(data.encode())
    return encrypted_data

def decrypt_data(encrypted_data):
    decrypted_data = cipher.decrypt(encrypted_data).decode()
    return decrypted_data

def has_valid_api_key(chat_id):
    if current_openai_key:
        return is_valid_openai_key(current_openai_key)
    api_key = get_api_key_from_db(chat_id)
    return is_valid_openai_key(api_key)

def get_api_key_from_db(chat_id):
    global current_openai_key
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute("SELECT encrypted_openai_api_key FROM users WHERE chat_id = %s", (chat_id,))
    encrypted_api_key = cursor.fetchone()
    cursor.close()
    cnx.close()

    if encrypted_api_key is None or not encrypted_api_key[0]:
        return None

    decrypted_key = decrypt_data(encrypted_api_key[0])
    current_openai_key = decrypted_key 
    return decrypted_key

def store_api_key_in_db(chat_id, api_key):
    encrypted_api_key = encrypt_data(api_key)
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute("INSERT INTO users (chat_id, encrypted_openai_api_key) VALUES (%s, %s) ON DUPLICATE KEY UPDATE encrypted_openai_api_key = %s", 
                   (chat_id, encrypted_api_key, encrypted_api_key))
    cnx.commit()
    cursor.close()
    cnx.close()

def store_provided_key(message):
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id=chat_id)  

    api_key = message.text
    if message.text == "NO":
        bot.clear_step_handler_by_chat_id(chat_id=chat_id)
        bot.send_message(chat_id, operation_cancelled)
        return    
    if is_valid_openai_key(api_key):
        store_api_key_in_db(chat_id, api_key)
        bot.reply_to(message, key_stored)
    else:
        bot.reply_to(message, invalid_api_key)
        bot.register_next_step_handler(message, store_provided_key)  

def is_valid_openai_key(api_key):
    openai.api_key = api_key
    try:
        models = openai.Model.list()
        if models:  
            return True
    except Exception as e:
        logger.error( "%s %s", "Error during OpenAI API call:", e)
        return False 

def remove_phrases(text):
    for phrase in phrases:
        text = text.replace(phrase, "")
    return text

def generate_corrected_transcript(temperature, system_prompt, audio_file):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": audio_file
            }
        ]
    )
    return response['choices'][0]['message']['content']

def change_api_key_step(message):
    new_api_key = message.text
    chat_id = message.chat.id
    if message.text == "NO":
        bot.clear_step_handler_by_chat_id(chat_id=chat_id)
        bot.send_message(chat_id, operation_cancelled)
        return    
    if is_valid_openai_key(new_api_key):
        store_api_key_in_db(chat_id, new_api_key)
        bot.send_message(message.chat.id, key_updated)
    else:
        bot.send_message(message.chat.id, invalid_api_key)
        bot.register_next_step_handler(message, change_api_key_step)

def get_language_from_db(chat_id):
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute("SELECT language FROM users WHERE chat_id = %s", (chat_id,))
    lang = cursor.fetchone()
    cursor.close()
    cnx.close()
    return lang[0] if lang else "en"  

def store_language_in_db(chat_id, lang):
    cnx = mysql.connector.connect(**db_config)
    cursor = cnx.cursor()
    cursor.execute("INSERT INTO users (chat_id, language) VALUES (%s, %s) ON DUPLICATE KEY UPDATE language = %s", 
                   (chat_id, lang, lang))
    cnx.commit()
    cursor.close()
    cnx.close()

def load_language_resources(lang):
    global phrases, system_prompt, welcome_message, help_message, recognition_started, transcription_error
    global bot_connected_message, bot_connection_error, provide_api_key, invalid_api_key, key_stored
    global key_updated, operation_cancelled, language_choice, language_error, select_lang

    with open('languages.json', 'r') as lang_file:
        lang_resources = json.load(lang_file)
        phrases = lang_resources['phrases']
        system_prompt = lang_resources[lang]['system_prompt']
        welcome_message = lang_resources[lang]['welcome_message']
        help_message = lang_resources[lang]['help_message']
        recognition_started = lang_resources[lang]['recognition_started']
        transcription_error = lang_resources[lang]['transcription_error']
        provide_api_key = lang_resources[lang]['provide_api_key']
        invalid_api_key = lang_resources[lang]['invalid_api_key']
        key_stored = lang_resources[lang]['key_stored']
        key_updated = lang_resources[lang]['key_updated']
        operation_cancelled= lang_resources[lang]['operation_cancelled']
        language_choice = lang_resources[lang]['language_choice']
        language_error = lang_resources[lang]['language_error']
        select_lang = lang_resources[lang]['select_lang']

def set_language(message):
    global language
    chat_id = message.chat.id
    lang_choice = message.text

    if lang_choice in languages:
        language = languages[lang_choice]
        store_language_in_db(chat_id, language)
        load_language_resources(language)
        bot.send_message(chat_id, f"{language_choice} {lang_choice}!")

        markup = telebot.types.ReplyKeyboardRemove()

    else:
        bot.send_message(chat_id, language_error)
        send_language_keyboard(chat_id)

def send_language_keyboard(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for lang in languages:
        markup.add(lang)
    
    bot.send_message(chat_id, select_lang, reply_markup=markup)
    bot.register_next_step_handler_by_chat_id(chat_id, set_language)

@bot.message_handler(commands=["help"])
def send_help(message):
    global language
    chat_id = message.chat.id
    if not language:
        language = get_language_from_db(chat_id)
    load_language_resources(language)    
    bot.reply_to(
        message, help_message,
    )
@bot.message_handler(commands=["start"])
def send_welcome(message):
    global language
    chat_id = message.chat.id
    if not language:
        language = get_language_from_db(chat_id)
    load_language_resources(language)
    bot.reply_to(message, welcome_message)

@bot.message_handler(commands=["stop_bot"])
def stop_bot_handler(message):
    bot.stop_bot()

@bot.message_handler(commands=["changekey"])
def change_api_key_command(message):
    global language
    chat_id = message.chat.id
    if not language:
        language = get_language_from_db(chat_id)
    load_language_resources(language)    
    bot.send_message(message.chat.id, provide_api_key)
    bot.register_next_step_handler(message, change_api_key_step)

@bot.message_handler(commands=["changelanguage"])
def change_language_command(message):
    global language
    chat_id = message.chat.id
    if not language:
        language = get_language_from_db(chat_id)
    load_language_resources(language)    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for lang_name in languages:
        markup.add(telebot.types.KeyboardButton(lang_name))
    bot.send_message(message.chat.id, select_lang, reply_markup=markup)
    bot.register_next_step_handler(message, set_language)


@bot.message_handler(content_types=['voice'])
def get_voice_message(message):
    global language
    chat_id = message.chat.id
    if not language:
        language = get_language_from_db(chat_id)
    load_language_resources(language) 
    if current_openai_key is None:
        api_key = get_api_key_from_db(chat_id)
        if not has_valid_api_key(chat_id):
            bot.reply_to(message, provide_api_key)
            bot.register_next_step_handler(message, store_provided_key)
            return
    else:
        api_key = current_openai_key
        
    file_info = bot.get_file(message.voice.file_id)
    file_path = file_info.file_path
    openai.api_key = api_key
    file_url = f'https://api.telegram.org/file/bot{bot_token}/{file_path}'

    logger.info('Downloading audio file...')
    audio_file = requests.get(file_url)

    file_extension = file_path.split('.')[-1]
    file_name = f'{str(uuid.uuid4())}.{file_extension}'
    with open(file_name, 'wb') as f:
        f.write(audio_file.content)

    sent_message = bot.reply_to(message, recognition_started, parse_mode='Markdown')
    logger.info('Converting audio file in MP3 format...')
    mp3_file_name = f'{str(uuid.uuid4())}.mp3'
    subprocess.run(['ffmpeg', '-i', file_name, mp3_file_name])

    transcript = None
    try:
        with open(mp3_file_name, "rb") as audio_file:
            transcript = openai.Audio.transcribe(
                file=audio_file,
                model="whisper-1",
                response_format="text"
            )
            logger.debug(transcript)
            transcript = remove_phrases(transcript)
            logger.debug(transcript)
            if transcript is not None and transcript.strip():
                corrected_text = generate_corrected_transcript(0, system_prompt, transcript)
                logger.debug(corrected_text)
                bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=corrected_text)
            else:
                bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error)
    except Exception as e:
        logger.error("%s %s", "Error transcribing audio file:", e)
        bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error)

    logger.info('Deleting audio file...')
    os.remove(file_name)
    os.remove(mp3_file_name)

    logger.info("%s %s", 'Original file name:', file_name)
    logger.info("%s %s", 'Converted file name:', mp3_file_name)

bot.polling()
