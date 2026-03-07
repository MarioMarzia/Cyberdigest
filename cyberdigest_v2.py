#!/usr/bin/env python3
"""
CyberDigest v2.0 - Digest quotidiano di cybersicurezza con approfondimenti didattici

Modalità:
  --digest    : Genera e invia il digest giornaliero (per cron)
  --bot       : Avvia il bot Telegram in ascolto continuo
  --cleanup   : Pulisce articoli più vecchi di 7 giorni

Repository: https://github.com/yourusername/cyberdigest
"""

import feedparser
import trafilatura
import requests
import json
import re
import os
import sqlite3
import argparse
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple
from difflib import SequenceMatcher
from pathlib import Path

# Carica variabili da .env se presente (opzionale)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv non installato, usa solo variabili d'ambiente

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAZIONE
# ═══════════════════════════════════════════════════════════════════════════════

# --- LLM Locale (Llama 3.1) ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = "llama3.1:8b-instruct-q4_K_M"

# --- Gemini API (backup) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# --- Groq API (per approfondimenti - VELOCE!) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Processing ---
CHUNK_SIZE = 900
CHUNK_OVERLAP = 100
MAX_ARTICLES_PER_FEED = 10
REQUEST_TIMEOUT = 15
GEMINI_SCORE_THRESHOLD = 8  # Usa Gemini per riassunti con score >= 8

# --- Storage ---
DB_PATH = Path(__file__).parent / "cyberdigest.db"
RETENTION_DAYS = 7

# --- Interessi personali (per boost scoring) ---
PERSONAL_INTERESTS = {
    "red_team": [
        "red team", "penetration test", "pentest", "offensive security",
        "lateral movement", "privilege escalation", "post-exploitation",
        "cobalt strike", "metasploit", "mimikatz", "bloodhound",
        "phishing", "social engineering", "initial access", "persistence",
        "defense evasion", "credential access", "c2", "command and control"
    ],
    "malware": [
        "malware", "ransomware", "trojan", "backdoor", "rootkit",
        "infostealer", "stealer", "loader", "dropper", "rat",
        "reverse engineering", "malware analysis", "sandbox", "unpacking",
        "obfuscation", "packer", "shellcode", "payload", "implant",
        "apt", "threat actor", "campaign"
    ],
    "ai_security": [
        "ai security", "machine learning", "llm", "artificial intelligence",
        "adversarial", "prompt injection", "model", "neural network",
        "deepfake", "ai-powered", "automated", "ml-based"
    ]
}

INTEREST_BOOST = 2  # Punti extra per match con interessi

# --- Feed RSS ---
FEEDS = [
    # Breaking & News
    ("The Hacker News",         "https://feeds.feedburner.com/TheHackersNews",              "breaking"),
    ("BleepingComputer",        "https://www.bleepingcomputer.com/feed/",                   "breaking"),
    ("Krebs on Security",       "https://krebsonsecurity.com/feed/",                        "breaking"),
    ("CyberScoop",              "https://cyberscoop.com/feed/",                             "breaking"),
    ("The Cyber Express",       "https://thecyberexpress.com/feed/",                        "breaking"),
    ("GBHackers",               "https://gbhackers.com/feed/",                              "breaking"),
    # Threat Intel & Research
    ("CrowdStrike Blog",        "https://www.crowdstrike.com/en-us/blog/feed/",             "threat_intel"),
    ("Sophos News",             "https://news.sophos.com/en-us/feed/",                      "threat_intel"),
    ("Dark Reading",            "https://www.darkreading.com/rss.xml",                      "threat_intel"),
    ("ANY.RUN Blog",            "https://any.run/cybersecurity-blog/feed/",                 "threat_intel"),
    ("Cyble Research (CRIL)",   "https://cyble.com/feed/",                                  "threat_intel"),
    ("Schneier on Security",    "https://www.schneier.com/feed/",                           "threat_intel"),
    # OffSec & Exploitation
    ("OffSec Blog",             "https://www.offsec.com/blog/feed/",                        "offsec"),
    ("Full Disclosure",         "https://seclists.org/rss/fulldisclosure.rss",              "offsec"),
    ("Hack The Box Blog",       "https://www.hackthebox.com/rss/blog/all",                  "offsec"),
    ("Exploit-DB",              "https://www.exploit-db.com/rss.xml",                       "offsec"),
    ("Packet Storm",            "https://packetstormsecurity.com/feeds/",                   "offsec"),
    # Istituzionale & CVE
    ("CISA Alerts",             "https://www.cisa.gov/cybersecurity-advisories/all.xml",   "istituzionale"),
    ("Google Security Blog",    "https://feeds.feedburner.com/GoogleOnlineSecurityBlog",   "istituzionale"),
    ("Help Net Security",       "https://helpnetsecurity.com/feed/",                        "istituzionale"),
]

CATEGORY_LABELS = {
    "breaking":       "🚨 Breaking News & Threat Actors",
    "threat_intel":   "🔬 Threat Intelligence & Research",
    "offsec":         "🛠️ OffSec & Exploitation",
    "istituzionale":  "🏛️ CVE, Advisory & Compliance",
}

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

def init_database():
    """Inizializza il database SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source TEXT,
            category TEXT,
            score INTEGER,
            interest_boost INTEGER DEFAULT 0,
            matched_interests TEXT,
            summary TEXT,
            key_concepts TEXT,
            full_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gemini_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tokens_used INTEGER,
            operation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_created 
        ON articles(created_at)
    """)
    
    conn.commit()
    conn.close()

def save_article(article: dict) -> int:
    """Salva un articolo nel database e ritorna l'ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO articles 
            (title, url, source, category, score, interest_boost, matched_interests, 
             summary, key_concepts, full_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article["title"],
            article["url"],
            article.get("source", ""),
            article.get("category", ""),
            article.get("score", 5),
            article.get("interest_boost", 0),
            json.dumps(article.get("matched_interests", [])),
            article.get("summary", ""),
            json.dumps(article.get("key_concepts", [])),
            article.get("full_text", ""),
            datetime.now()
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_today_articles() -> List[dict]:
    """Recupera gli articoli di oggi."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    today = datetime.now().date()
    cursor.execute("""
        SELECT * FROM articles 
        WHERE date(created_at) = date(?)
        ORDER BY (score + interest_boost) DESC
    """, (today,))
    
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for art in articles:
        art["matched_interests"] = json.loads(art.get("matched_interests", "[]"))
        art["key_concepts"] = json.loads(art.get("key_concepts", "[]"))
    
    return articles

def get_article_by_id(article_id: int) -> Optional[dict]:
    """Recupera un articolo specifico per ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        article = dict(row)
        article["matched_interests"] = json.loads(article.get("matched_interests", "[]"))
        article["key_concepts"] = json.loads(article.get("key_concepts", "[]"))
        return article
    return None

def search_articles(keyword: str) -> List[dict]:
    """Cerca articoli per keyword."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM articles 
        WHERE title LIKE ? OR summary LIKE ? OR key_concepts LIKE ?
        ORDER BY created_at DESC
        LIMIT 10
    """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
    
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for art in articles:
        art["matched_interests"] = json.loads(art.get("matched_interests", "[]"))
        art["key_concepts"] = json.loads(art.get("key_concepts", "[]"))
    
    return articles

def log_gemini_usage(tokens: int, operation: str):
    """Logga l'utilizzo di Gemini."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO gemini_usage (tokens_used, operation) VALUES (?, ?)",
        (tokens, operation)
    )
    conn.commit()
    conn.close()

def get_weekly_gemini_stats() -> dict:
    """Statistiche utilizzo Gemini dell'ultima settimana."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    week_ago = datetime.now() - timedelta(days=7)
    cursor.execute("""
        SELECT SUM(tokens_used) as total, COUNT(*) as calls
        FROM gemini_usage
        WHERE created_at >= ?
    """, (week_ago,))
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        "total_tokens": row[0] or 0,
        "total_calls": row[1] or 0
    }

def cleanup_old_articles():
    """Elimina articoli più vecchi di RETENTION_DAYS."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    cursor.execute("DELETE FROM articles WHERE created_at < ?", (cutoff,))
    deleted = cursor.rowcount
    
    cursor.execute("DELETE FROM gemini_usage WHERE created_at < ?", (cutoff,))
    
    conn.commit()
    conn.close()
    
    return deleted

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def is_within_24h(entry) -> bool:
    """Controlla se un articolo è stato pubblicato nelle ultime 24 ore."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            pub = datetime(*t[:6], tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - pub <= timedelta(hours=24)
    return True

def scrape_article(url: str) -> Optional[str]:
    """Scarica il testo completo di un articolo."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded, 
                include_comments=False,
                include_tables=False, 
                no_fallback=False
            )
            return text
    except Exception:
        pass
    return None

def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE,
                      overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Divide il testo in chunk con overlap."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks

def calculate_interest_match(text: str, title: str) -> Tuple[int, List[str]]:
    """
    Calcola il boost basato sugli interessi personali.
    Ritorna (boost_points, lista_interessi_matchati)
    """
    combined = (text + " " + title).lower()
    matched = []
    
    for interest_name, keywords in PERSONAL_INTERESTS.items():
        for kw in keywords:
            if kw.lower() in combined:
                if interest_name not in matched:
                    matched.append(interest_name)
                break
    
    boost = len(matched) * INTEREST_BOOST
    return boost, matched

def extract_key_concepts(text: str, title: str) -> List[str]:
    """Estrae concetti chiave dal testo per approfondimenti."""
    concepts = []
    
    # Pattern per CVE
    cves = re.findall(r'CVE-\d{4}-\d+', text, re.IGNORECASE)
    concepts.extend(list(set(cves))[:3])
    
    # Termini tecnici comuni da evidenziare
    tech_terms = [
        "dll sideloading", "dll hijacking", "process injection", 
        "credential dumping", "kerberoasting", "pass the hash",
        "golden ticket", "silver ticket", "dcsync", "zerologon",
        "living off the land", "lolbins", "fileless malware",
        "supply chain", "watering hole", "spear phishing",
        "command and control", "c2", "exfiltration",
        "ransomware", "double extortion", "data leak",
        "zero-day", "0-day", "rce", "remote code execution",
        "sql injection", "xss", "csrf", "ssrf", "idor",
        "buffer overflow", "heap spray", "rop chain",
        "sandbox evasion", "anti-analysis", "obfuscation",
        "lateral movement", "privilege escalation", "persistence"
    ]
    
    text_lower = text.lower()
    for term in tech_terms:
        if term in text_lower and term not in [c.lower() for c in concepts]:
            concepts.append(term.title())
            if len(concepts) >= 5:
                break
    
    return concepts

# ═══════════════════════════════════════════════════════════════════════════════
# POST-PROCESSING: Correzione termini tecnici
# ═══════════════════════════════════════════════════════════════════════════════

# Dizionario di sostituzione: italiano → inglese
TERM_CORRECTIONS = {
    # Exploit e vulnerabilità
    "catene di exploit": "exploit chain",
    "catena di exploit": "exploit chain",
    "catene di attacco": "exploit chain",
    "catena di attacco": "exploit chain",
    "catene di sfruttamento": "exploit chain",
    "catena di sfruttamento": "exploit chain",
    "kit di sfruttamento": "exploit kit",
    "kit di exploit": "exploit kit",
    "confusione di tipo": "type confusion",
    "confusione del tipo": "type confusion",
    "uso dopo la liberazione": "use-after-free",
    "uso dopo il rilascio": "use-after-free",
    "overflow del buffer": "buffer overflow",
    "overflow di buffer": "buffer overflow",
    "traboccamento del buffer": "buffer overflow",
    "giorno zero": "zero-day",
    "giorni zero": "zero-day",
    "0-day": "zero-day",
    "iniezione di comando": "command injection",
    "iniezione di comandi": "command injection",
    "iniezione di SQL": "SQL injection",
    "iniezione SQL": "SQL injection",
    
    # Obfuscation
    "confusione del flusso di controllo": "control flow obfuscation",
    "offuscamento del codice": "code obfuscation",
    "offuscamento": "obfuscation",
    
    # Esecuzione e privilegi
    "esecuzione remota del codice": "RCE",
    "esecuzione di codice remoto": "RCE",
    "esecuzione remota di codice": "RCE",
    "esecuzione di codice da remoto": "RCE",
    "esecuzione codice remoto": "RCE",
    "esecuzione di codice arbitrario": "RCE",
    "esecuzione di comandi arbitrari": "arbitrary command execution",
    "elevazione dei privilegi": "privilege escalation",
    "elevazione di privilegi": "privilege escalation",
    "escalation dei privilegi": "privilege escalation",
    "aumento dei privilegi": "privilege escalation",
    "fuga dalla sandbox": "sandbox escape",
    "evasione dalla sandbox": "sandbox escape",
    "uscita dalla sandbox": "sandbox escape",
    "bypass della sandbox": "sandbox escape",
    
    # APT e Threat actor
    "attività di minaccia persistente (APT)": "APT (Advanced Persistent Threat)",
    "attività di minaccia persistente": "APT",
    "minaccia persistente avanzata": "APT",
    "attori malintenzionati": "threat actor",
    "attore malintenzionato": "threat actor",
    "attori malevoli": "threat actor",
    "attore malevolo": "threat actor",
    "attori della minaccia": "threat actor",
    "attore della minaccia": "threat actor",
    "attori minacciosi": "threat actor",
    "attore minaccioso": "threat actor",
    "attori di minaccia": "threat actor",
    "attore di minaccia": "threat actor",
    "attori statali": "state-sponsored threat actor",
    "attore statale": "state-sponsored threat actor",
    "stato-sponsorizzato": "state-sponsored",
    "sponsorizzato dallo stato": "state-sponsored",
    "finanziato dallo stato": "state-sponsored",
    
    # Malware e payload
    "carico utile": "payload",
    "carico malevolo": "payload",
    "codice malevolo": "malicious code",
    "codice malizioso": "malicious code",
    "software malevolo": "malware",
    "software malizioso": "malware",
    "programma malevolo": "malware",
    "pacchetti maliziosi": "malicious packages",
    "pacchetto malizioso": "malicious package",
    "librerie maliziose": "malicious libraries",
    "porta secondaria": "backdoor",
    "porta di servizio": "backdoor",
    "cavallo di troia": "trojan",
    
    # Tecniche
    "movimento laterale": "lateral movement",
    "spostamento laterale": "lateral movement",
    "iniezione di processo": "process injection",
    "iniezione di codice": "code injection",
    "comando e controllo": "C2",
    "server di comando e controllo": "C2 server",
    "infrastruttura di comando": "C2 infrastructure",
    "esfiltrazione dei dati": "data exfiltration",
    "esfiltrazione di dati": "data exfiltration",
    "furto di credenziali": "credential theft",
    "dumping delle credenziali": "credential dumping",
    "esfiltrare": "exfiltrate",
    
    # Bypass e evasione
    "bypass del PAC": "PAC bypass",
    "aggiramento del PAC": "PAC bypass",
    "bypass del controllo": "bypass",
    "evasione del rilevamento": "detection evasion",
    "evasione della difesa": "defense evasion",
    "tecniche di evasione": "evasion techniques",
    "evadere le misure di sicurezza": "evade security measures",
    
    # Persistenza
    "meccanismo di persistenza": "persistence mechanism",
    "persistenza sul sistema": "persistence",
    
    # Errori comuni
    "PAC (Proxy Auto-Configuration)": "PAC (Pointer Authentication Code)",
    "Proxy Auto-Configuration": "Pointer Authentication Code",
    
    # Duplicati da parentesi
    "exploit chain (exploit chain)": "exploit chain",
    "type confusion (type confusion)": "type confusion",
    "RCE (RCE)": "RCE",
    "threat actor (threat actor)": "threat actor",
    "(RCE)": "",  # Rimuove duplicato
    "l'RCE (RCE)": "RCE",
    
    # Supply chain
    "catena di approvvigionamento": "supply chain",
    "attacco alla catena di fornitura": "supply chain attack",
}

def fix_technical_terms(text: str) -> str:
    """
    Post-processing: sostituisce i termini tecnici tradotti in italiano
    con i corretti termini inglesi.
    """
    result = text
    
    # Applica le sostituzioni (case-insensitive per le chiavi)
    for italian, english in TERM_CORRECTIONS.items():
        # Sostituzione case-insensitive
        pattern = re.compile(re.escape(italian), re.IGNORECASE)
        result = pattern.sub(english, result)
    
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# LLM CALLS
# ═══════════════════════════════════════════════════════════════════════════════

def ollama_call(prompt: str, system: str = "", retries: int = 2) -> str:
    """Chiamata all'API di Ollama (Hermes locale)."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 1024}
    }
    
    for attempt in range(retries):
        try:
            r = requests.post(OLLAMA_URL, json=payload, timeout=300)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                print(f"  ⚠ Timeout Ollama, retry {attempt+2}/{retries}...")
                continue
            return "[TIMEOUT]"
        except Exception as e:
            return f"[ERRORE LLM: {e}]"
    return "[ERRORE: retry falliti]"

def gemini_call(prompt: str, system: str = "") -> Tuple[str, int]:
    """
    Chiamata all'API di Gemini.
    Ritorna (risposta, token_usati)
    """
    url = f"{GEMINI_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    # Combina system prompt e user prompt
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    
    payload = {
        "contents": [{
            "parts": [{"text": full_prompt}]
        }],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 8192
        }
    }
    
    # Retry logic
    for attempt in range(2):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=180)
            r.raise_for_status()
            data = r.json()
            
            # Estrai risposta
            response_text = ""
            if "candidates" in data and data["candidates"]:
                candidate = data["candidates"][0]
                # Controlla se la risposta è stata troncata
                finish_reason = candidate.get("finishReason", "")
                parts = candidate.get("content", {}).get("parts", [])
                response_text = "".join(p.get("text", "") for p in parts)
                
                if finish_reason == "MAX_TOKENS":
                    response_text += "\n\n⚠️ _Risposta troncata per limite token_"
            
            # Stima token usati
            tokens_used = len(full_prompt.split()) + len(response_text.split())
            
            return response_text.strip(), tokens_used
            
        except requests.exceptions.Timeout:
            if attempt == 0:
                print(f"  ⚠ Timeout Gemini, retry...")
                continue
            return "[ERRORE: Timeout - la risposta era troppo lunga. Riprova con /approfondisci]", 0
        except Exception as e:
            print(f"  ⚠ Errore Gemini: {e}")
            return f"[ERRORE GEMINI: {e}]", 0
    
    return "[ERRORE: tutti i retry falliti]", 0

def groq_call(prompt: str, system: str = "") -> Tuple[str, int]:
    """
    Chiamata all'API di Groq (VELOCE!).
    Ritorna (risposta, token_usati)
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 6000  # Aumentato per approfondimenti più completi
    }
    
    try:
        print(f"[GROQ] Invio richiesta...")
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        print(f"[GROQ] Status code: {r.status_code}")
        r.raise_for_status()
        data = r.json()
        
        # Estrai risposta
        response_text = ""
        if "choices" in data and data["choices"]:
            response_text = data["choices"][0].get("message", {}).get("content", "")
            print(f"[GROQ] Risposta ricevuta: {len(response_text)} caratteri")
            
            # Controlla se troncata
            finish_reason = data["choices"][0].get("finish_reason", "")
            if finish_reason == "length":
                response_text += "\n\n⚠️ _Risposta troncata per limite token_"
        else:
            print(f"[GROQ] Nessuna risposta in choices: {data}")
        
        # Token usati
        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)
        
        return response_text.strip(), tokens_used
        
    except requests.exceptions.Timeout:
        print("[GROQ] Timeout!")
        return "[ERRORE: Timeout Groq - riprova]", 0
    except Exception as e:
        print(f"[GROQ] Errore: {e}")
        return f"[ERRORE GROQ: {e}]", 0

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def summarize_with_local_llm(title: str, url: str, full_text: str) -> dict:
    """
    Riassunto con LLM locale (Llama 3.1) + post-processing per termini tecnici.
    """
    system_prompt = """Sei un analista senior di threat intelligence che scrive briefing formali per un team di security.

REGOLE FONDAMENTALI:
1. Scrivi in ITALIANO ma TUTTI i termini tecnici devono restare in INGLESE:
   - exploit, exploit chain, payload, C2, RCE, LPE, zero-day, n-day
   - type confusion, use-after-free, buffer overflow, heap spray
   - sandbox escape, privilege escalation, lateral movement
   - threat actor, APT, implant, loader, dropper, backdoor
   - CVE, IOC, TTP, PAC bypass, KASLR, ASLR
   - WebKit, kernel, userland, jailbreak, Lockdown Mode

2. Tono FORMALE e PROFESSIONALE, come un report aziendale
3. NO traduzioni dei termini tecnici (scrivi "exploit chain" non "catena di exploit")
4. Sii preciso e conciso"""

    chunks = split_into_chunks(full_text)
    
    if len(chunks) == 1:
        # Articolo corto: riassunto diretto
        prompt = f"""Articolo: "{title}"

TESTO:
{chunks[0]}

Scrivi un briefing formale in italiano (150-200 parole) con questa struttura:

**Sintesi**
Cosa è successo o è stato scoperto. 2-3 frasi dirette.

**Analisi Tecnica**
Dettagli tecnici: CVE, tecniche di attacco, malware, IOC. Tutti i termini tecnici in inglese (type confusion, RCE, exploit chain, PAC bypass, sandbox escape, ecc.).

**Threat Actor & Impatto**
Chi è coinvolto (threat actor, APT) e quali sono le vittime/conseguenze.

**Contromisure**
Una raccomandazione SPECIFICA e CONCRETA. Non generica. Esempio: "Aggiornare a iOS 17.3+ che patcha CVE-2024-23222" oppure "Abilitare Lockdown Mode per ridurre la attack surface".

REGOLE:
- Italiano formale, termini tecnici in inglese
- NO ripetizioni
- Tono professionale da report"""
        
        summary = ollama_call(prompt, system_prompt)
    else:
        # Articolo lungo: chunking
        partial_summaries = []
        for i, chunk in enumerate(chunks[:4]):  # Max 4 chunks
            prompt = f"""Segmento {i+1}/{min(len(chunks), 4)} di "{title}":

{chunk}

Estrai i fatti chiave in 2-3 frasi. Italiano formale, termini tecnici in inglese (type confusion, RCE, exploit chain, threat actor, C2, payload, sandbox escape, PAC bypass). No ripetizioni."""
            
            summary = ollama_call(prompt, system_prompt)
            partial_summaries.append(summary)
        
        # Merge
        merged = "\n".join(partial_summaries)
        merge_prompt = f"""Questi sono estratti dall'articolo "{title}":

{merged}

Scrivi un briefing formale unificato in italiano (150-200 parole):

**Sintesi**
Evento principale in 2-3 frasi.

**Analisi Tecnica**
Dettagli tecnici con termini in inglese (type confusion, RCE, exploit chain, ecc.)

**Threat Actor & Impatto**
Chi è coinvolto e conseguenze.

**Contromisure**
Raccomandazione SPECIFICA (es: "Aggiornare a versione X.Y che patcha CVE-XXX")

REGOLE:
- Italiano formale, termini tecnici in inglese
- NO ripetizioni
- Tono professionale"""
        
        summary = ollama_call(merge_prompt, system_prompt)
    
    # Calcola score
    score = calculate_score_local(title, summary)
    
    # Estrai concetti chiave
    key_concepts = extract_key_concepts(full_text, title)
    
    # Calcola boost interessi
    boost, matched = calculate_interest_match(full_text, title)
    
    # POST-PROCESSING: correggi termini tecnici tradotti
    summary = fix_technical_terms(summary)
    
    return {
        "title": title,
        "url": url,
        "score": score,
        "interest_boost": boost,
        "matched_interests": matched,
        "summary": summary,
        "key_concepts": key_concepts,
        "full_text": full_text[:5000]  # Tronca per storage
    }

def calculate_score_local(title: str, summary: str) -> int:
    """Calcola score di importanza con LLM locale."""
    prompt = f"""Valuta l'importanza di questa notizia di cybersicurezza (1-10).

Titolo: {title}
Riassunto: {summary[:500]}

SCALA:
9-10: Zero-day critico attivamente sfruttato, APT nation-state, breach massivo
7-8: Vulnerabilità alta con exploit pubblico, campagna malware attiva, ransomware importante  
5-6: Vulnerabilità media, ricerca interessante, nuovo tool/tecnica
3-4: News di settore, prodotti, conferenze
1-2: Contenuto generico, marketing

Rispondi SOLO con un numero intero."""
    
    score_raw = ollama_call(prompt)
    try:
        score = int(re.search(r'\d+', score_raw).group())
        return max(1, min(10, score))
    except:
        return 5

def generate_deep_dive(article: dict) -> str:
    """
    Genera un approfondimento didattico partendo dall'ARTICOLO ORIGINALE.
    Spiega i concetti tecnici trovati nell'articolo in modo approfondito.
    """
    system = """Sei un esperto di cybersecurity che spiega concetti tecnici a studenti di livello intermedio.

REGOLE:
1. Scrivi in ITALIANO ma TUTTI i termini tecnici in INGLESE
2. Tono formale ma accessibile
3. Spiega i concetti come se il lettore li incontrasse per la prima volta, ma senza essere banale
4. Dai sempre esempi pratici
5. NON iniziare con saluti o introduzioni
6. Vai dritto al contenuto"""

    concepts = article.get("key_concepts", [])
    concepts_str = ", ".join(concepts) if concepts else "concetti tecnici presenti"
    
    # Usa il testo ORIGINALE dell'articolo, non il summary
    full_text = article.get('full_text', '')
    if not full_text or len(full_text) < 100:
        full_text = article.get('summary', '')
    
    prompt = f"""ARTICOLO ORIGINALE: "{article['title']}"

TESTO COMPLETO:
{full_text[:4000]}

CONCETTI TECNICI IDENTIFICATI: {concepts_str}

---

Analizza l'articolo e scrivi un APPROFONDIMENTO DIDATTICO completo.

STRUTTURA DA SEGUIRE:

📌 PANORAMICA
Breve contesto generale: cosa è successo, perché è rilevante. (3-4 frasi)

🔬 CONCETTI TECNICI SPIEGATI
Per OGNI concetto tecnico importante trovato nell'articolo:

• [Nome del concetto in inglese]
  - Cos'è: spiegazione chiara del concetto
  - Come funziona: il meccanismo tecnico
  - Esempio pratico: come viene usato in questo caso specifico o in generale

Analizza tutti i concetti rilevanti: CVE specifiche, tecniche di attacco, malware, vulnerabilità, ecc.

🔴 OFFENSIVE SECURITY
Come un attaccante potrebbe sfruttare quanto descritto:
- Tool utilizzabili (nomi specifici)
- Tecniche correlate
- Riferimenti MITRE ATT&CK se applicabili

🛡️ DEFENSIVE SECURITY  
Come difendersi:
- IOC da monitorare
- Detection: cosa cercare nei log
- Mitigazioni concrete e specifiche

IMPORTANTE:
- La lunghezza dipende da quanti concetti tecnici ci sono: più concetti = risposta più lunga
- Spiega TUTTI i concetti tecnici importanti, non solo alcuni
- Ogni spiegazione deve essere comprensibile ma tecnicamente accurata
- Termini tecnici sempre in inglese"""

    response, tokens = groq_call(prompt, system)
    log_gemini_usage(tokens, "deep_dive_groq")
    
    return response

# ═══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

def deduplicate(articles: List[dict], threshold: int = 75) -> List[dict]:
    """
    Deduplicazione migliorata: raggruppa articoli simili.
    Threshold abbassato per catturare più duplicati.
    """
    seen_titles = []
    seen_urls = set()
    result = []
    
    for art in articles:
        # Skip URL duplicati
        if art["url"] in seen_urls:
            continue
        
        title_lower = art["title"].lower()
        
        # Check similarità titolo
        duplicate = False
        for seen in seen_titles:
            ratio = SequenceMatcher(None, title_lower, seen).ratio() * 100
            if ratio >= threshold:
                duplicate = True
                break
        
        if not duplicate:
            seen_titles.append(title_lower)
            seen_urls.add(art["url"])
            result.append(art)
    
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def send_telegram(text: str, parse_mode: str = "Markdown"):
    """Invia messaggio su Telegram con gestione messaggi lunghi."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Telegram limite 4096 caratteri
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    
    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code != 200:
                # Riprova senza parse_mode se Markdown fallisce
                payload["parse_mode"] = None
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")
        time.sleep(0.5)  # Rate limiting

def format_article_message(article: dict, index: int = None) -> str:
    """Formatta un articolo per Telegram."""
    # Header con score
    score = article.get("score", 5)
    boost = article.get("interest_boost", 0)
    total_score = score + boost
    
    score_str = f"⭐ {score}/10"
    if boost > 0:
        interests = article.get("matched_interests", [])
        interests_emoji = {"red_team": "🔴", "malware": "🦠", "ai_security": "🤖"}
        interest_icons = "".join(interests_emoji.get(i, "🎯") for i in interests)
        score_str += f" (+{boost} {interest_icons})"
    
    # Index per riferimento
    idx_str = f"[{index}] " if index else ""
    
    # Concetti chiave
    concepts = article.get("key_concepts", [])
    concepts_str = ""
    if concepts:
        concepts_str = f"\n🔑 *Concetti:* {', '.join(concepts)}"
    
    msg = f"""{idx_str}*{article['title']}*
{score_str} | 📡 {article.get('source', 'Unknown')}
🔗 {article['url']}{concepts_str}

{article.get('summary', 'Nessun riassunto disponibile.')}

{'─' * 25}"""
    
    return msg

# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT (modalità interattiva)
# ═══════════════════════════════════════════════════════════════════════════════

class TelegramBot:
    """Bot Telegram in polling per comandi interattivi."""
    
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        self.offset = 0
        self.running = False
    
    def get_updates(self) -> List[dict]:
        """Recupera nuovi messaggi."""
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.offset, "timeout": 30}
        
        try:
            r = requests.get(url, params=params, timeout=35)
            data = r.json()
            
            if data.get("ok") and data.get("result"):
                updates = data["result"]
                if updates:
                    self.offset = updates[-1]["update_id"] + 1
                return updates
        except Exception as e:
            print(f"[BOT] Errore polling: {e}")
        
        return []
    
    def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown"):
        """Invia risposta."""
        url = f"{self.base_url}/sendMessage"
        
        # Splitta in chunk da 4000 caratteri (Telegram limite 4096)
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        
        print(f"[BOT] Invio messaggio: {len(text)} caratteri, {len(chunks)} chunk(s)")
        
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True
            }
            
            # Aggiungi parse_mode solo se specificato
            if parse_mode:
                payload["parse_mode"] = parse_mode
            
            try:
                r = requests.post(url, json=payload, timeout=30)
                if r.status_code != 200:
                    print(f"[BOT] Errore Telegram (chunk {i+1}): {r.status_code} - {r.text[:200]}")
                    # Riprova senza parse_mode
                    if parse_mode:
                        payload.pop("parse_mode", None)
                        r2 = requests.post(url, json=payload, timeout=30)
                        if r2.status_code != 200:
                            print(f"[BOT] Errore anche senza Markdown: {r2.status_code}")
                else:
                    print(f"[BOT] Chunk {i+1}/{len(chunks)} inviato OK")
            except Exception as e:
                print(f"[BOT] Errore invio chunk {i+1}: {e}")
            time.sleep(0.3)
    
    def handle_command(self, chat_id: int, text: str):
        """Gestisce i comandi."""
        text = text.strip()
        
        if text.startswith("/start") or text.startswith("/help"):
            self.cmd_help(chat_id)
        elif text.startswith("/lista"):
            self.cmd_lista(chat_id)
        elif text.startswith("/approfondisci"):
            self.cmd_approfondisci(chat_id, text)
        elif text.startswith("/cerca"):
            self.cmd_cerca(chat_id, text)
        elif text.startswith("/stats"):
            self.cmd_stats(chat_id)
        else:
            self.send_message(chat_id, "Comando non riconosciuto. Usa /help per la lista comandi.")
    
    def cmd_help(self, chat_id: int):
        """Mostra help."""
        msg = """🤖 *CyberDigest Bot - Comandi*

/lista - Mostra le news di oggi con numeri
/approfondisci [numero] - Approfondimento didattico su una news
/cerca [termine] - Cerca nelle news salvate
/stats - Statistiche utilizzo Gemini
/help - Questo messaggio

*Esempio:*
`/approfondisci 3` → Approfondisce la news #3
`/cerca ransomware` → Cerca news sul ransomware"""
        
        self.send_message(chat_id, msg)
    
    def cmd_lista(self, chat_id: int):
        """Lista news di oggi."""
        articles = get_today_articles()
        
        if not articles:
            self.send_message(chat_id, "📭 Nessuna news per oggi. Il digest viene generato alle 3:00.")
            return
        
        msg = f"📰 *News di oggi* ({len(articles)} articoli)\n\n"
        
        for i, art in enumerate(articles, 1):
            score = art.get("score", 5) + art.get("interest_boost", 0)
            interests = art.get("matched_interests", [])
            interest_str = " 🎯" if interests else ""
            
            msg += f"*[{i}]* {art['title'][:60]}...\n"
            msg += f"    ⭐ {score}/10{interest_str} | {art.get('source', '')}\n\n"
        
        msg += "\n_Usa /approfondisci [numero] per il deep dive_"
        self.send_message(chat_id, msg)
    
    def cmd_approfondisci(self, chat_id: int, text: str):
        """Genera approfondimento con Groq."""
        # Estrai numero
        match = re.search(r'/approfondisci\s+(\d+)', text)
        
        if not match:
            self.send_message(chat_id, "⚠️ Specifica il numero della news.\nEsempio: `/approfondisci 3`")
            return
        
        idx = int(match.group(1))
        articles = get_today_articles()
        
        if idx < 1 or idx > len(articles):
            self.send_message(chat_id, f"⚠️ Numero non valido. Scegli tra 1 e {len(articles)}.")
            return
        
        article = articles[idx - 1]
        
        self.send_message(chat_id, f"🔄 Analizzando l'articolo originale:\n*{article['title']}*\n\n_Generazione approfondimento in corso..._")
        
        # Genera deep dive con Groq
        print(f"[BOT] Chiamando Groq per approfondimento...")
        deep_dive = generate_deep_dive(article)
        print(f"[BOT] Risposta Groq ricevuta: {len(deep_dive)} caratteri")
        
        # Controlla se c'è un errore
        if deep_dive.startswith("[ERRORE"):
            self.send_message(chat_id, f"❌ {deep_dive}")
            return
        
        header = f"📚 APPROFONDIMENTO DIDATTICO\n\n{article['title']}\n🔗 {article['url']}\n\n{'═' * 25}\n\n"
        
        full_message = header + deep_dive
        
        # Invia SENZA Markdown per evitare errori di parsing
        self.send_message(chat_id, full_message, parse_mode=None)
    
    def cmd_cerca(self, chat_id: int, text: str):
        """Cerca nelle news."""
        match = re.search(r'/cerca\s+(.+)', text)
        
        if not match:
            self.send_message(chat_id, "⚠️ Specifica cosa cercare.\nEsempio: `/cerca ransomware`")
            return
        
        keyword = match.group(1).strip()
        articles = search_articles(keyword)
        
        if not articles:
            self.send_message(chat_id, f"🔍 Nessun risultato per '{keyword}'")
            return
        
        msg = f"🔍 *Risultati per '{keyword}'* ({len(articles)})\n\n"
        
        for art in articles[:5]:
            date = art.get("created_at", "")[:10]
            msg += f"• *{art['title'][:50]}...*\n"
            msg += f"  {date} | ⭐ {art.get('score', 5)}/10\n"
            msg += f"  🔗 {art['url']}\n\n"
        
        self.send_message(chat_id, msg)
    
    def cmd_stats(self, chat_id: int):
        """Statistiche Gemini."""
        stats = get_weekly_gemini_stats()
        
        msg = f"""📊 *Statistiche Gemini (ultimi 7 giorni)*

🔢 Chiamate totali: {stats['total_calls']}
📝 Token utilizzati: {stats['total_tokens']:,}
📈 Media per chiamata: {stats['total_tokens'] // max(stats['total_calls'], 1):,} token

_Limite giornaliero Gemini 2.5 Flash: ~250k TPM_"""
        
        self.send_message(chat_id, msg)
    
    def run(self):
        """Avvia il bot in polling."""
        print(f"[{datetime.now()}] 🤖 Bot Telegram avviato in polling...")
        self.running = True
        
        while self.running:
            try:
                updates = self.get_updates()
                
                for update in updates:
                    if "message" not in update:
                        continue
                    
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")
                    
                    # Verifica che sia il chat_id autorizzato
                    if str(chat_id) != TELEGRAM_CHAT_ID:
                        self.send_message(chat_id, "⛔ Non sei autorizzato ad usare questo bot.")
                        continue
                    
                    if text.startswith("/"):
                        print(f"[BOT] Comando ricevuto: {text}")
                        self.handle_command(chat_id, text)
                        
            except KeyboardInterrupt:
                print("\n[BOT] Interruzione richiesta...")
                self.running = False
            except Exception as e:
                print(f"[BOT] Errore: {e}")
                time.sleep(5)
    
    def stop(self):
        """Ferma il bot."""
        self.running = False

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE (digest giornaliero)
# ═══════════════════════════════════════════════════════════════════════════════

def run_digest():
    """Pipeline principale per il digest giornaliero."""
    print(f"\n[{datetime.now()}] ▶ Avvio CyberDigest v2.0 pipeline...")
    
    init_database()
    
    # 1. Raccolta feed RSS
    print("[1/5] 📡 Raccolta feed RSS...")
    raw_articles = []
    
    for name, url, category in FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if not is_within_24h(entry):
                    continue
                if count >= MAX_ARTICLES_PER_FEED:
                    break
                raw_articles.append({
                    "title": entry.get("title", "No title"),
                    "url": entry.get("link", ""),
                    "source": name,
                    "category": category,
                    "summary": entry.get("summary", "")
                })
                count += 1
            print(f"  ✓ {name}: {count} articoli")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
    
    print(f"  → Totale raccolti: {len(raw_articles)}")
    
    # 2. Deduplicazione preliminare
    print("[2/5] 🔄 Deduplicazione preliminare...")
    raw_articles = deduplicate(raw_articles)
    print(f"  → Dopo dedup: {len(raw_articles)}")
    
    # 3. Scraping full-text
    print("[3/5] 📄 Scraping full-text...")
    for i, art in enumerate(raw_articles):
        print(f"  [{i+1}/{len(raw_articles)}] {art['title'][:50]}...")
        full_text = scrape_article(art["url"])
        art["full_text"] = full_text if full_text else art["summary"]
    
    # 4. Elaborazione LLM
    print("[4/5] 🧠 Elaborazione LLM...")
    processed = {cat: [] for cat in CATEGORY_LABELS}
    
    for i, art in enumerate(raw_articles):
        print(f"  [{i+1}/{len(raw_articles)}] {art['title'][:50]}...")
        
        result = summarize_with_local_llm(art["title"], art["url"], art["full_text"])
        result["source"] = art["source"]
        result["category"] = art["category"]
        
        # Salva nel database
        article_id = save_article(result)
        result["id"] = article_id
        
        processed[art["category"]].append(result)
    
    # 5. Ordinamento per score totale (base + boost)
    print("[5/5] 📊 Ordinamento e invio...")
    for category in processed:
        processed[category].sort(
            key=lambda x: x.get("score", 0) + x.get("interest_boost", 0),
            reverse=True
        )
    
    # Invio digest
    date_str = datetime.now().strftime("%d/%m/%Y")
    total_articles = sum(len(arts) for arts in processed.values())
    
    header = f"""📰 *CYBERDIGEST v2.0 — {date_str}*
_Digest quotidiano con focus su Red Team, Malware & IA_
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 {total_articles} news | 🔴 Red Team | 🦠 Malware | 🤖 IA

_Usa /lista per vedere i numeri, /approfondisci N per deep dive_
"""
    send_telegram(header)
    
    article_counter = 1
    
    for category, label in CATEGORY_LABELS.items():
        articles = processed.get(category, [])
        if not articles:
            continue
        
        section_header = f"\n{label}\n{'━' * 30}"
        send_telegram(section_header)
        
        for art in articles:
            msg = format_article_message(art, article_counter)
            send_telegram(msg)
            article_counter += 1
            time.sleep(0.5)
    
    # Footer
    stats = get_weekly_gemini_stats()
    footer = f"""
✅ *Digest completato* — {total_articles} articoli elaborati
📊 Gemini questa settimana: {stats['total_calls']} chiamate, {stats['total_tokens']:,} token

💡 _Rispondi con /approfondisci [numero] per una mini-lezione!_"""
    
    send_telegram(footer)
    print(f"[{datetime.now()}] ✅ CyberDigest completato!")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def validate_config():
    """Verifica che le variabili di configurazione necessarie siano impostate."""
    errors = []
    
    if not TELEGRAM_TOKEN:
        errors.append("TELEGRAM_TOKEN non configurato")
    if not TELEGRAM_CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID non configurato")
    if not GROQ_API_KEY:
        errors.append("GROQ_API_KEY non configurato (necessario per /approfondisci)")
    
    if errors:
        print("❌ Errori di configurazione:")
        for err in errors:
            print(f"   • {err}")
        print("\n💡 Configura le variabili d'ambiente o crea un file .env")
        print("   Vedi README.md per istruzioni dettagliate.")
        return False
    return True

def main():
    parser = argparse.ArgumentParser(
        description="CyberDigest v2.0 - Digest quotidiano di cybersicurezza",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python cyberdigest.py --digest     # Genera e invia il digest
  python cyberdigest.py --bot        # Avvia bot Telegram
  python cyberdigest.py --cleanup    # Pulisce articoli vecchi
  
Configurazione:
  Imposta le variabili d'ambiente prima di eseguire:
  export TELEGRAM_TOKEN="your_token"
  export TELEGRAM_CHAT_ID="your_chat_id"
  export GROQ_API_KEY="your_groq_key"
  export OLLAMA_URL="http://127.0.0.1:11434/api/generate"  # opzionale
        """
    )
    
    parser.add_argument("--digest", action="store_true",
                        help="Genera e invia il digest giornaliero")
    parser.add_argument("--bot", action="store_true",
                        help="Avvia il bot Telegram in ascolto")
    parser.add_argument("--cleanup", action="store_true",
                        help="Elimina articoli più vecchi di 7 giorni")
    
    args = parser.parse_args()
    
    # Valida configurazione per comandi che la richiedono
    if args.digest or args.bot:
        if not validate_config():
            return
    
    # Inizializza sempre il database
    init_database()
    
    if args.cleanup:
        deleted = cleanup_old_articles()
        print(f"🗑️ Eliminati {deleted} articoli vecchi")
    elif args.bot:
        bot = TelegramBot()
        bot.run()
    elif args.digest:
        run_digest()
    else:
        # Default: mostra help
        parser.print_help()

if __name__ == "__main__":
    main()
