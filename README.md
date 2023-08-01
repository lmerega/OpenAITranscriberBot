# Welcome to StackEdit!


# Telegram Audio Transcription Bot

## Description
This project is a Telegram bot built using the `telebot` Python library and OpenAI's GPT-3.5-turbo and Whisper-1 models. It is designed to receive voice messages, transcribe them, process the transcription with the GPT-3.5-turbo model, and send the result back to the user. It supports multiple languages for system prompts and error messages.

## Requirements
* Python 3.6+
* telebot library
* requests library
* openai library
* ffmpeg for audio conversion

## Installation

```sh
pip install pyTelegramBotAPI requests openai
```

*Note: ffmpeg needs to be installed separately, please refer to the official ffmpeg [installation guide](https://ffmpeg.org/download.html).*

## Setup

1. Obtain an API key from OpenAI at their [developer site](https://beta.openai.com/signup/).
2. Generate a Telegram Bot token following Telegram's [BotFather guide](https://core.telegram.org/bots#6-botfather).
3. Clone this repository and create a file named `config.json` in the root directory. The structure of `config.json` should be:
```json
{
    "openai_api_key": "your_openai_api_key",
    "bot_token": "your_telegram_bot_token"
}
```
4. To add or modify supported languages, you can modify the `languages.json` file in the root directory. The structure of `languages.json` is as follows:
```json
{
    "it": {
        "system_prompt": "Italian_system_prompt",
        "welcome_message": "Italian_welcome_message",
        "recognition_started": "Italian_recognition_started_message",
        "transcription_error": "Italian_transcription_error_message",
        "bot_connected_message": "Italian_bot_connected_message",
        "bot_connection_error": "Italian_bot_connection_error_message"
    },
    "en": {...}
}
```
5. Replace `language = "it"` in the code with the language code you want to use for system messages.

## Usage
1. Start your bot by running `python main.py` (or your script file's name).
2. In the Telegram app, search for your bot's username and start a chat with it.
3. The bot accepts `/start` and `/help` commands, which will display a welcome message. It also responds to voice messages, transcribing and processing them.

## Functions

- `remove_phrases(text)`: This function removes specific phrases from the text (defined in the `phrases` list).

- `generate_corrected_transcript(temperature, system_prompt, audio_file)`: This function uses OpenAI's GPT-3.5-turbo model to process the transcribed text.

- `send_welcome(message)`: This function handles the `/start` and `/help` commands.

- `get_voice_message(message)`: This function handles voice messages. It downloads the audio, transcribes it, processes the transcription with GPT-3.5-turbo, and sends back the result.

## Disclaimer

This project uses OpenAI's GPT-3.5-turbo and Whisper-1 models, which may incur costs. Please refer to OpenAI's [pricing](https://openai.com/pricing) for more information.

## License

This project is licensed under the terms of the MIT license.
