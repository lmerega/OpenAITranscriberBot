# Telegram Audio Transcriber Bot

Bot Telegram per la trascrizione di messaggi vocali e file audio con Google Speech-to-Text V2.

Il core attuale del progetto e' basato su Google Speech-to-Text V2, con gestione quote mensili, utenti illimitati e report amministrativi.

## Funzionalita'

- Trascrizione di `voice`, `audio` e documenti audio.
- Gestione lingua utente.
- Limite mensile di 10 minuti per gli utenti normali.
- Whitelist di utenti illimitati.
- Report `/usage` per l'amministratore con totali mensili, giornalieri e storico.
- Messaggio automatico in inglese per i nuovi utenti con spiegazione del limite mensile.

## File principali

- `transcriberBot.py`: logica del bot.
- `languages.json`: testi multilingua.
- `config.example.json`: esempio di configurazione locale.
- `requirements.txt`: dipendenze Python minime del bot.
- `schema.sql`: schema MySQL minimo.
- `systemd/telegram-audio-transcriber-bot.service.example`: esempio di service per Linux.

## Architettura attuale

- Telegram gestisce l'ingresso dei messaggi vocali e dei file audio.
- `ffmpeg` converte l'audio in WAV PCM mono preservando la frequenza di campionamento quando possibile.
- Google Speech-to-Text V2 esegue la trascrizione.
- Gli audio fino a 60 secondi vengono inviati direttamente a V2.
- Gli audio piu' lunghi vengono spezzati localmente in chunk e trascritti in sequenza.
- MySQL conserva utenti, consumo mensile e storico interazioni.
- Il bot applica quote mensili agli utenti normali e report dettagliati all'amministratore.

## File locali esclusi dal repository

Questi file restano locali e non vanno pubblicati:

- `config.json`
- `google-credentials.json`
- log, cache e virtualenv
- script locali non legati al bot principale

## Setup locale

1. Crea un virtualenv.
2. Installa le dipendenze:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

3. Copia `config.example.json` in `config.json` e inserisci i valori reali.
   `admin_chat_id` e `unlimited_chat_ids` devono restare solo nella configurazione privata locale.
4. Assicurati che `ffmpeg` sia installato sul sistema.
5. Crea il database e importa lo schema:

```bash
mysql -u USER -p DATABASE_NAME < schema.sql
```

6. Avvia il bot:

```bash
python3 transcriberBot.py
```

## Note operative

- Il bot usa MySQL e si aspetta tabelle compatibili con `users`, `monthly_usage` e `interactions`.
- `google-credentials.json` deve restare fuori da Git.
- Gli ID Telegram privati non devono essere hardcodati nel codice: vanno tenuti solo in `config.json`.
- Prima di pubblicare il progetto e' consigliato ruotare tutti i segreti gia' comparsi nei file locali.
