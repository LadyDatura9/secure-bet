"""
Portale SecureBet — Server Flask
Backend: polling The Odds API + profilo utente con API key
Avvio: python3 server.py → apre su http://localhost:5000
"""
import json
import os
import threading
import time
import urllib.request
import urllib.parse

from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

# ── Config ──
API_KEY = "35c0397e2f44fd0472606b27c83eda0e"  # dal dashboard the-odds-api.com
SPORT = "soccer"
REGION = "eu"
MERCATI = ["h2h_1x2"]
POLLING_INTERVAL = 3600  # secondi (~1 ora, dato 500 crediti/mese)

# ── Stato condiviso ──
ultimo_risultato = {"eventi": [], "aggiornato": None}
in_corso = False


def prendi_quote():
    """Chiede le quote pre-match da The Odds API."""
    params = urllib.parse.urlencode({
        "apiKey": API_KEY,
        "sport": SPORT,
        "region": REGION,
        "markets": ",".join(MERCATI),
    })
    url = f"https://api.the-odds-api.com/v4/odds?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def elabora(eventi_da_api):
    """Normalizza gli eventi e rileva le surebet."""
    risultati = []
    for ev in eventi_da_api:
        nome = f"{ev.get('home_team','?')} vs {ev.get('away_team','?')}"
        quote = []
        for mkt in ev.get("markets", []):
            for q in mkt.get("quotes", []):
                esito = q.get("outcome", "")
                quota = q.get("price", 0)
                book = q.get("book", "")
                if quota and esito:
                    quote.append({"esito": esito, "quota": quota, "book": book})
        if len(quote) < 2:
            continue
        # Miglior quota per esito
        miglior = {}
        for q in quote:
            e = q["esito"]
            if e not in miglior or q["quota"] > miglior[e]["quota"]:
                miglior[e] = q
        quote_migliori = list(miglior.values())
        somma_prob = sum(1 / q["quota"] for q in quote_migliori)
        esiste = somma_prob < 1.0
        profitto_pct = round((1 / somma_prob - 1) * 100, 2) if esiste else 0
        risultati.append({
            "evento": nome,
            "esiste": esiste,
            "somma_prob": round(somma_prob, 4),
            "profitto_pct": profitto_pct,
            "quote": quote_migliori,
        })
    return risultati


def polling_loop():
    """Loop di polling in background."""
    while True:
        try:
            dati = prendi_quote()
            ultimo_risultato["eventi"] = elabora(dati)
            ultimo_risultato["aggiornato"] = time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as ex:
            # Senza Internet (sandbox) o key non valida: non crash
            ultimo_risultato["errore"] = str(ex)
        time.sleep(POLLING_INTERVAL)


# ── Rothe ──

@app.route("/")
def index():
    return render_template("index.html",
                           eventi=ultimo_risultato["eventi"],
                           aggiornato=ultimo_risultato.get("aggiornato"),
                           errore=ultimo_risultato.get("errore"))


@app.route("/profilo")
def profilo():
    return render_template("profilo.html")


@app.route("/profilo/salva", methods=["POST"])
def profilo_salva():
    betfair = request.form.get("betfair_key", "").strip()
    singbet = request.form.get("singbet_key", "").strip()
    # In produzione: si cifrano col server (AES-256) e si salvano nel DB
    # Qui (demo): si salvano in una variabile globale
    # (in produzione: DB SQLite o Postgres)
    globale_keys["betfair"] = betfair
    globale_keys["singbet"] = singbet
    return redirect(url_for("profilo"))


@app.route("/api/quote")
def api_quote():
    """Endpoint API per il frontend (JS): restituisce gli eventi + surebet."""
    return jsonify(ultimo_risultato)


# Avvia il thread di polling al lancio
threading.Thread(target=polling_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
