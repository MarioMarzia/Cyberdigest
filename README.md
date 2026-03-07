# 🛡️ CyberDigest v2.0

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-green.svg)](https://ollama.ai/)
[![Groq](https://img.shields.io/badge/Groq-Cloud%20API-orange.svg)](https://groq.com/)

**Digest quotidiano di cybersecurity con approfondimenti didattici interattivi**

Sistema automatizzato per raccogliere, riassumere e spiegare le ultime notizie di sicurezza informatica, con focus su Red Team, Malware Analysis e AI Security.

---

## 🚀 Quick Start

```bash
# 1. Clona il repository
git clone https://github.com/yourusername/cyberdigest.git
cd cyberdigest

# 2. Installa dipendenze
pip install -r requirements.txt

# 3. Configura le credenziali
cp .env.example .env
nano .env  # Inserisci le tue API keys

# 4. Scarica il modello Ollama
ollama pull llama3.1:8b-instruct-q4_K_M

# 5. Esegui il digest
python3 cyberdigest_v2.py --digest
```

---

## 📋 Indice

- [Funzionalità](#-funzionalità)
- [Architettura](#-architettura)
- [Requisiti](#-requisiti)
- [Configurazione](#-configurazione)
- [Utilizzo](#-utilizzo)
- [Comandi Telegram](#-comandi-telegram)
- [Struttura Output](#-struttura-output)
- [Sistema di Scoring](#-sistema-di-scoring)
- [Post-Processing Termini Tecnici](#-post-processing-termini-tecnici)
- [Storage](#-storage)
- [Crontab Setup](#-crontab-setup)
- [Troubleshooting](#-troubleshooting)
- [Personalizzazione](#-personalizzazione)

---

## ✨ Funzionalità

### Digest Automatico
- Raccolta automatica da **20+ feed RSS** di cybersecurity
- Riassunti in **italiano formale** con termini tecnici in inglese
- **Deduplicazione** intelligente degli articoli simili (soglia 75%)
- **Scoring personalizzato** basato sui tuoi interessi
- Invio automatico su **Telegram**

### Bot Interattivo
| Comando | Descrizione |
|---------|-------------|
| `/lista` | Visualizza le news del giorno |
| `/approfondisci [n]` | Approfondimento didattico completo |
| `/cerca [termine]` | Ricerca nelle news salvate |
| `/stats` | Statistiche utilizzo API |
| `/help` | Lista comandi |

### Approfondimenti Didattici
- Analisi dell'**articolo originale** (non del riassunto)
- Spiegazione dettagliata di **tutti i concetti tecnici**
- Prospettiva **Offensive Security** (Red Team)
- Prospettiva **Defensive Security** (Blue Team)
- Riferimenti **MITRE ATT&CK**

---

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│                      CYBERDIGEST v2.0                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  20+ Feed    │───▶│  Scraping    │───▶│  Dedup 75%   │      │
│  │  RSS         │    │  Trafilatura │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                 │               │
│                                                 ▼               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              LLAMA 3.1 8B (Locale via Ollama)               ││
│  │  • Riassunti per TUTTI gli articoli                         ││
│  │  • Scoring base                                             ││
│  │  • Estrazione concetti chiave                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              POST-PROCESSING AUTOMATICO                     ││
│  │  • ~80 sostituzioni termini tecnici                         ││
│  │  • "catene di exploit" → "exploit chain"                    ││
│  │  • "esecuzione remota del codice" → "RCE"                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    SQLite Database                          ││
│  │  • Articoli con metadati  • Tracking API  • Retention 7gg   ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│              ┌───────────────┴───────────────┐                  │
│              ▼                               ▼                  │
│  ┌───────────────────┐           ┌───────────────────┐         │
│  │  Digest Telegram  │           │  Bot Interattivo  │         │
│  │  (cron notturno)  │           │  /approfondisci   │         │
│  └───────────────────┘           └─────────┬─────────┘         │
│                                            │                    │
│                                            ▼                    │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              GROQ API (Llama 3.3 70B)                       ││
│  │  • Solo per /approfondisci on-demand                        ││
│  │  • Approfondimenti didattici completi                       ││
│  │  • Ultra-veloce (2-5 secondi)                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Requisiti

### Dipendenze Python
```bash
pip install -r requirements.txt
```

Oppure manualmente:
```bash
pip install feedparser trafilatura requests python-dotenv
```

### Servizi Esterni
| Servizio | Descrizione | Costo |
|----------|-------------|-------|
| [Ollama](https://ollama.ai/) | LLM locale per riassunti | Gratuito |
| [Groq](https://console.groq.com/) | LLM cloud per approfondimenti | Gratuito (1000 req/giorno) |
| [Telegram Bot](https://core.telegram.org/bots) | Invio messaggi | Gratuito |

---

## ⚙️ Configurazione

### Metodo 1: File .env (consigliato)

```bash
# Copia il template
cp .env.example .env

# Modifica con i tuoi valori
nano .env
```

### Metodo 2: Variabili d'ambiente

```bash
export TELEGRAM_TOKEN="your_telegram_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export GROQ_API_KEY="gsk_your_groq_api_key"
export OLLAMA_URL="http://127.0.0.1:11434/api/generate"  # opzionale
```

### Ottenere le credenziali

#### Telegram Bot
1. Cerca `@BotFather` su Telegram
2. Invia `/newbot` e segui le istruzioni
3. Copia il token
4. Per ottenere il tuo `chat_id`, scrivi al bot e visita:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

#### Groq API Key
1. Vai su https://console.groq.com
2. Crea un account (gratuito)
3. Genera una API key

#### Ollama
```bash
# Installa Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Scarica il modello
ollama pull llama3.1:8b-instruct-q4_K_M
```

---

## 🚀 Utilizzo

### Modalità Digest
```bash
python3 cyberdigest_v2.py --digest
```
Genera e invia il digest completo su Telegram.

### Modalità Bot
```bash
python3 cyberdigest_v2.py --bot
```
Avvia il bot Telegram in polling per comandi interattivi.

### Pulizia Database
```bash
python3 cyberdigest_v2.py --cleanup
```
Elimina articoli più vecchi di 7 giorni.

---

## 🤖 Comandi Telegram

### Workflow tipico

1. Ricevi il digest automatico alle 3:00 di notte
2. Vedi una news interessante (es. #3)
3. Scrivi `/approfondisci 3`
4. Ricevi l'approfondimento completo con:
   - Spiegazione di ogni concetto tecnico
   - Prospettiva Red Team (come sfruttare)
   - Prospettiva Blue Team (come difendersi)
   - Riferimenti MITRE ATT&CK

---

## 📄 Struttura Output

### Digest (Riassunto)

```
1 Titolo Articolo
⭐ 8/10 (+4 🔴🦠) | 📡 The Hacker News
🔗 https://example.com/article
🔑 Concetti: CVE-2024-XXXX, RCE, C2

**Sintesi**
Cosa è successo in 2-3 frasi.

**Analisi Tecnica**
Dettagli tecnici con termini in inglese (exploit chain, RCE, PAC bypass, ecc.)

**Threat Actor & Impatto**
Chi è coinvolto e conseguenze.

**Contromisure**
Raccomandazione specifica (es: "Aggiornare a iOS 17.3+")
```

### Approfondimento (`/approfondisci`)

```
📌 PANORAMICA
Contesto generale: cosa è successo, perché è rilevante.

🔬 CONCETTI TECNICI SPIEGATI
Per ogni concetto:
• [Nome in inglese]
  - Cos'è: spiegazione chiara
  - Come funziona: meccanismo tecnico
  - Esempio pratico: applicazione nel caso specifico

🔴 OFFENSIVE SECURITY
- Tool utilizzabili (Metasploit, Cobalt Strike, ecc.)
- Tecniche correlate
- Riferimenti MITRE ATT&CK

🛡️ DEFENSIVE SECURITY
- IOC da monitorare
- Cosa cercare nei log
- Mitigazioni concrete
```

---

## 🎯 Sistema di Scoring

### Score Base (1-10)

| Score | Significato |
|-------|-------------|
| 9-10 | Zero-day critico, APT nation-state, breach massivo |
| 7-8 | Vulnerabilità alta con exploit pubblico, campagna malware attiva |
| 5-6 | Vulnerabilità media, ricerca interessante |
| 3-4 | News di settore, prodotti |
| 1-2 | Contenuto generico, marketing |

### Boost Interessi Personali (+2 per match)

| Interesse | Emoji | Keywords esempio |
|-----------|-------|------------------|
| **Red Team** | 🔴 | penetration test, lateral movement, C2, Cobalt Strike... |
| **Malware** | 🦠 | ransomware, trojan, reverse engineering, APT... |
| **AI Security** | 🤖 | LLM, prompt injection, adversarial ML... |

**Esempio:** News con score 6 che parla di malware → `6 + 2 = 8` → Mostrato come `⭐ 8/10 (+2 🦠)`

---

## 🔧 Post-Processing Termini Tecnici

Il sistema applica automaticamente ~80 sostituzioni per garantire che i termini tecnici siano sempre in inglese:

| Italiano (errato) | Inglese (corretto) |
|-------------------|-------------------|
| catene di exploit | exploit chain |
| confusione di tipo | type confusion |
| esecuzione remota del codice | RCE |
| elevazione dei privilegi | privilege escalation |
| attori malintenzionati | threat actor |
| fuga dalla sandbox | sandbox escape |
| giorno zero | zero-day |
| movimento laterale | lateral movement |
| iniezione di comando | command injection |
| ... | (~80 sostituzioni totali) |

Per aggiungere nuove sostituzioni, modifica il dizionario `TERM_CORRECTIONS` nel codice.

---

## 💾 Storage

### Database SQLite (`cyberdigest.db`)

**Tabella `articles`:**
| Campo | Descrizione |
|-------|-------------|
| `id` | ID univoco |
| `title` | Titolo articolo |
| `url` | URL originale |
| `source` | Fonte RSS |
| `category` | Categoria (breaking, threat_intel, offsec, istituzionale) |
| `score` | Score base (1-10) |
| `interest_boost` | Boost da interessi personali |
| `matched_interests` | Interessi matchati (JSON) |
| `summary` | Riassunto generato |
| `key_concepts` | Concetti chiave estratti (JSON) |
| `full_text` | Testo completo (max 5000 caratteri) |
| `created_at` | Timestamp |

### Retention
- Articoli eliminati automaticamente dopo **7 giorni**
- Cleanup manuale: `python3 cyberdigest_v2.py --cleanup`

---

## ⏰ Crontab Setup

```bash
crontab -e
```

```cron
# Digest ogni notte alle 3:00
0 3 * * * /usr/bin/python3 /path/to/cyberdigest_v2.py --digest >> /var/log/cyberdigest.log 2>&1

# Cleanup ogni domenica alle 4:00
0 4 * * 0 /usr/bin/python3 /path/to/cyberdigest_v2.py --cleanup >> /var/log/cyberdigest.log 2>&1
```

### Bot come servizio systemd

```bash
sudo nano /etc/systemd/system/cyberdigest-bot.service
```

```ini
[Unit]
Description=CyberDigest Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/script/
ExecStart=/usr/bin/python3 /path/to/cyberdigest_v2.py --bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable cyberdigest-bot
sudo systemctl start cyberdigest-bot
```

---

## 🐛 Troubleshooting

### Il bot non risponde
```bash
# Verifica che sia in esecuzione
ps aux | grep cyberdigest

# Controlla i log
journalctl -u cyberdigest-bot -f

# Verifica che non ci siano altri bot sullo stesso token
```

### Errori Ollama
```bash
# Verifica che Ollama sia attivo
curl http://localhost:11434/api/tags

# Il modello è caricato?
ollama list

# Prova il modello
ollama run llama3.1:8b-instruct-q4_K_M
```

### Errori Groq
- Verifica API key valida
- Controlla `/stats` per vedere l'utilizzo
- Limite: 1000 richieste/giorno

### Articoli in inglese invece che italiano
- Il post-processing dovrebbe correggere i termini
- Se trovi nuovi termini tradotti male, aggiungili al dizionario `TERM_CORRECTIONS`

---

## 📡 Feed RSS Configurati

<details>
<summary><b>Clicca per vedere tutti i feed</b></summary>

### Breaking News
- The Hacker News
- BleepingComputer
- Krebs on Security
- CyberScoop
- The Cyber Express
- GBHackers

### Threat Intelligence
- CrowdStrike Blog
- Sophos News
- Dark Reading
- ANY.RUN Blog
- Cyble Research
- Schneier on Security

### OffSec & Exploitation
- OffSec Blog
- Full Disclosure
- Hack The Box Blog
- Exploit-DB
- Packet Storm

### Istituzionale & CVE
- CISA Alerts
- Google Security Blog
- Help Net Security

</details>

---

## 📝 Personalizzazione

### Aggiungere nuovi interessi

```python
PERSONAL_INTERESTS = {
    "red_team": [...],
    "malware": [...],
    "ai_security": [...],
    # Aggiungi:
    "cloud_security": [
        "aws", "azure", "kubernetes", "container",
        "s3 bucket", "iam", "serverless"
    ]
}
```

### Aggiungere feed RSS

```python
FEEDS = [
    # ...esistenti...
    ("Nome Feed", "https://url/feed.rss", "categoria"),
]
```

Categorie disponibili: `breaking`, `threat_intel`, `offsec`, `istituzionale`

### Aggiungere termini al post-processing

```python
TERM_CORRECTIONS = {
    # ...esistenti...
    "nuovo termine italiano": "english term",
}
```

---

## 🗺️ Roadmap

- [ ] Supporto multi-lingua per i riassunti
- [ ] Dashboard web per visualizzazione
- [ ] Export in formato newsletter
- [ ] Integrazione con Slack/Discord
- [ ] Machine Learning per scoring automatico

---

## 📜 Licenza

Uso personale ed educativo.

---

## 🙏 Credits

| Componente | Tecnologia |
|------------|------------|
| LLM Locale | [Llama 3.1 8B](https://ollama.ai/) via Ollama |
| LLM Cloud | [Llama 3.3 70B](https://groq.com/) via Groq |
| Scraping | [Trafilatura](https://github.com/adbar/trafilatura) |
| Feed Parsing | [Feedparser](https://github.com/kurtmckee/feedparser) |
