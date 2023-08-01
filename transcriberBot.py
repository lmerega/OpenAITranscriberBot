import telebot
import requests
import openai
import subprocess
import os
import uuid
import json

with open('config.json') as config_file:
    config = json.load(config_file)

with open('languages.json') as lang_file:
    lang_resources = json.load(lang_file)    

openai.api_key = config['openai_api_key']
bot_token = config['bot_token'] 

phrases = lang_resources['phrases']
language = "it"
system_prompt = lang_resources[language]['system_prompt']
welcome_message = lang_resources[language]['welcome_message']
recognition_started = lang_resources[language]['recognition_started']
transcription_error = lang_resources[language]['transcription_error']
bot_connected_message = lang_resources[language]['bot_connected_message'] 
bot_connection_error = lang_resources[language]['bot_connection_error']

bot = telebot.TeleBot(bot_token)

try:
    bot_info = bot.get_me()
    print(bot_connected_message, bot_info.id)
except Exception as e:
    print(bot_connection_error, e)

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

@bot.message_handler(commands=["help", "start"])
def send_welcome(message):
    bot.reply_to(
        message, welcome_message,
    )
@bot.message_handler(commands=["stop_bot"])
def stop_bot_handler(message):
    bot.stop_bot()

@bot.message_handler(content_types=['voice'])
def get_voice_message(message):
    print('Received audio file')

    file_info = bot.get_file(message.voice.file_id)
    file_path = file_info.file_path

    file_url = f'https://api.telegram.org/file/bot{bot_token}/{file_path}'

    print('Downloading audio file...')
    audio_file = requests.get(file_url)

    file_extension = file_path.split('.')[-1]
    file_name = f'{str(uuid.uuid4())}.{file_extension}'
    with open(file_name, 'wb') as f:
        f.write(audio_file.content)

    sent_message = bot.reply_to(message, recognition_started, parse_mode='Markdown')
    print('Converting audio file in MP3 format...')
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
            print(transcript)
            transcript = remove_phrases(transcript)
            print(transcript)
            if transcript is not None and transcript.strip():
                corrected_text = generate_corrected_transcript(0, system_prompt, transcript)
                print(corrected_text)
                bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=corrected_text)
            else:
                bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error)
    except Exception as e:
        print("Error transcribing audio file:", e)
        bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=transcription_error)

    print('Deleting audio file...')
    os.remove(file_name)
    os.remove(mp3_file_name)

    print('Original file name:', file_name)
    print('Converted file name:', mp3_file_name)

bot.polling()
