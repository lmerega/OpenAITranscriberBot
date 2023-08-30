# Telegram Audio Transcription Bot

## Description

Introducing the Telegram Audio Transcription Bot: a cutting-edge solution that uses the `telebot` Python library in tandem with OpenAI's GPT-3.5-turbo and Whisper-1 models. It's designed to transcribe voice messages, refine these transcriptions using the GPT-3.5-turbo model, and then send back polished results to the user. The bot's multi-language support is exemplary; it automatically detects user language preferences and delivers translated system prompts and error messages for an enhanced user experience. Prioritizing user data security, the bot encrypts individual OpenAI API keys in the database.

**Live Version:** Experience the bot's capabilities first-hand at [https://t.me/lmewhisperbot](https://t.me/lmewhisperbot).

## Changelog

- **Version 2.0.0**:
  - Integrated multi-language support with automatic language detection.
  - Introduced new commands: `/changelanguage` allowing users to switch between supported languages and `/changekey` to update OpenAI API keys.
  - Enhanced data security with encryption of OpenAI API keys within the database.
  - Revamped system prompts and error messages for intuitive user interactions.
  - Strengthened error handling and integrated detailed logging for streamlined troubleshooting.
  - Optimized overall bot performance.

## Requirements

- Python 3.6+
- telebot library
- requests library
- openai library
- cryptography library
- mysql-connector library
- ffmpeg for audio conversion

## Installation

```sh
pip install pyTelegramBotAPI requests openai cryptography mysql-connector-python
```

*Note: ffmpeg must be installed separately. Please follow the official ffmpeg [installation guide](https://ffmpeg.org/download.html).*

## Setup

1. Secure an API key from OpenAI on their [developer site](https://beta.openai.com/signup/).
2. Generate a Telegram Bot token using Telegram's [BotFather guide](https://core.telegram.org/bots#6-botfather).
3. Clone this repository.
4. Configure MySQL and construct the needed database and tables. The **Database Setup** section provides thorough details.
5. In the root directory, construct a `config.json` following the structure below:

```json
{
    "encryption_key": "YOUR_GENERATED_ENCRYPTION_KEY",
    "openai_api_key": "your_openai_api_key",
    "bot_token": "your_telegram_bot_token",
    "db_config": {
        "host": "YOUR_DB_HOST",
        "user": "YOUR_DB_USER",
        "password": "YOUR_DB_PASSWORD",
        "database": "YOUR_DB_NAME"
    }
}
```

*Tip: For generating an `encryption_key`, utilize the `cryptography` library in Python. Details are available in the **Generating an `encryption_key`** section.*

6. Add or modify supported languages via the `languages.json` in the root directory.

## Database Setup

1. Activate the MySQL server.
2. Implement the SQL commands below to set up the necessary database and table:

```sql
CREATE DATABASE TranscriptionBotDB;

USE TranscriptionBotDB;

CREATE TABLE Users (
    user_id INT PRIMARY KEY,
    openai_api_key_encrypted BLOB NOT NULL,
    preferred_language VARCHAR(5) NOT NULL DEFAULT 'en'
);
```

Note: The `preferred_language` defaults to 'en' (English). Users can adjust this setting through the `/changelanguage` command.

## Usage

1. Start the bot with the command: `python main.py`.
2. On Telegram, find your bot using its username to begin a chat.
3. The bot recognizes the commands: `/start`, `/help`, `/changekey`, and `/changelanguage`:
   - `/start` & `/help`: Presents a warm welcome and essential instructions.
   - `/changekey`: Allows users to update their OpenAI API key.
   - `/changelanguage`: Enables users to select from a list of supported languages.

4. The bot is also proficient at managing voice messages, ensuring they are transcribed and enhanced using the OpenAI models.

## Functions

- `remove_phrases(text)`: Omit specific phrases from text.
- `generate_corrected_transcript(temperature, system_prompt, audio_file)`: Refines transcribed content through the GPT-3.5-turbo model.
- `send_welcome(message)`: Responds to the `/start` and `/help` commands.
- `get_voice_message(message)`: Manages voice messages, transcribing and processing them.
- `change_api_key_command(message)`: Enables users to modify their OpenAI API key stored in the database.

## Generating an `encryption_key`

For ensuring the utmost security of OpenAI API keys in the database, make use of Fernet symmetric encryption:

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

Incorporate this generated key as the `encryption_key` in your `config.json`.

## Disclaimer

The bot operates using OpenAI's GPT-3.5-turbo and Whisper-1 models. It's important to note that usage may lead to associated costs. Always check OpenAI's [pricing](https://openai.com/pricing) for detailed information.

## License

This project adheres to the terms of the MIT license.