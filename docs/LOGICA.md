# Skill Advisor — Analisi critica e logica

## 1. Analisi critica dell'idea

| Richiesta | Problema reale | Decisione |
|---|---|---|
| "Capisce in autonomia e in modo silente cosa si fa" | Una skill non gira in background: si attiva solo quando la sua descrizione combacia col compito. | Due livelli: **hook** in Claude Code (davvero automatico, a ogni messaggio) + **istruzione breve** nelle istruzioni personalizzate per Claude.ai / ChatGPT. |
| "Leggera e veloce" | Se il catalogo sta dentro la skill, cresce e invecchia. Se ogni messaggio chiama un LLM esterno, diventa lenta e costosa. | Skill minuscola; catalogo esterno compatto (< 100 KB); matching **locale** per parole chiave, zero chiamate a LLM. |
| "Archivio ufficiale, solo garantite" | "Ufficiale" va definito, altrimenti entra di tutto. Le descrizioni di skill di terzi sono testo non fidato (rischio prompt injection). | **Whitelist esplicita** di fonti (`sources.json`). Si parte solo da `anthropics/skills`. Testi ripuliti e troncati. |
| "Solo ultime versioni, le vecchie si eliminano" | Le skill spesso non hanno numero di versione. | L'indice viene **ricostruito da zero** a ogni giro: ciò che non è più nella fonte sparisce da solo. La "versione" è l'hash del contenuto di SKILL.md. Un `changelog.json` registra aggiunte/rimozioni/aggiornamenti. |
| "Si aggiorna costantemente" | Serve qualcosa online che giri da solo. | GitHub Actions ogni 6 ore. Se un giro fallisce o trova 0 skill, **non sovrascrive** l'indice buono (fail-safe). |
| Claude **e** ChatGPT | Formati diversi; ChatGPT non esegue script locali. | Stesso `index.json` per entrambi: Claude lo legge via script, ChatGPT via una Action (GET dell'URL). |
| Privacy | Mandare il contenuto della chat a un server terzo è un rischio. | Con l'indice statico il confronto avviene **sul dispositivo**: la chat non esce mai. |
| Fastidio | Suggerire a ogni messaggio diventa rumore. | Max 3 suggerimenti, soglia minima di pertinenza, niente ripetizioni di skill già installate o scartate. |

Nota: Claude propone già da sé alcune skill dal catalogo. Il valore aggiunto qui è: filtro severo, funzionamento anche su ChatGPT, controllo totale delle fonti.

## 2. Serve un server?

**No, non nella prima versione.** Basta:

- un repository GitHub (gratuito) che contiene `index/index.json`;
- una GitHub Action che lo rigenera ogni 6 ore;
- l'URL "raw" del file come unico punto di accesso.

GitHub fa da "server" gratis, con CDN, senza manutenzione né costi.

Un server vero (MCP) serve **solo se** in futuro volete:
- ricerca semantica (embedding) invece che per parole chiave;
- statistiche d'uso / classifiche;
- un catalogo che superi qualche migliaio di voci.

## 3. Architettura

```
sources.json ──► crawler/build_index.py ──► index/index.json + changelog.json
   (whitelist)      (GitHub Action ogni 6h)        (URL pubblico raw)
                                                         │
             ┌───────────────────────────────────────────┼──────────────────┐
             ▼                                           ▼                  ▼
  hook Claude Code                         skill Advisor (Claude)    Action ChatGPT
  (a ogni prompt, silenzioso)              scripts/suggest.py        GET index.json
```

## 4. Logica dettagliata

### Crawler (`crawler/build_index.py`)
1. Legge `sources.json`.
2. Per ogni fonte GitHub: prende l'ultimo commit del branch, l'albero dei file, ogni `SKILL.md` sotto il percorso indicato.
3. Estrae dal frontmatter `name` e `description`; scarta voci senza nome/descrizione.
4. Ripulisce i testi (niente markup, max 400 caratteri) e calcola parole chiave (senza stopword IT/EN).
5. Versione = hash del contenuto. Se due voci hanno lo stesso nome, tiene quella della fonte più affidabile.
6. Confronta con l'indice precedente → `changelog.json`.
7. Scrive l'indice solo se ha trovato almeno 1 skill.

### Suggeritore (`skill/scripts/suggest.py`)
1. Scarica l'indice (cache locale 6 h; se offline usa la cache).
2. Tokenizza il contesto (le ultime righe della richiesta).
3. Punteggio = parole in comune con nome (peso 3), parole chiave (peso 2), descrizione (peso 1), normalizzato.
4. Esclude skill già installate o scartate dall'utente.
5. Restituisce al massimo 3 voci sopra soglia, oppure nulla.

### Hook Claude Code (`hooks/suggest_hook.py`)
- Evento `UserPromptSubmit`: legge il prompt, chiama il suggeritore con soglia più alta, e solo se c'è un match forte aggiunge una riga di contesto invisibile per Claude ("potrebbe servire la skill X"). Timeout 2 s: non rallenta mai la chat.

## 5. Passo 1 di miglioramento (fatto)
- **Arricchimento** (`enrichment/skills.json`): per ogni skill categoria, vantaggio in una frase, frasi d'esempio IT/EN e casi in cui non serve. Legato all'hash della versione: se la skill cambia, il crawler la segnala come `stale`; se è nuova, come `missing`.
- **Abbinamento BM25** su nome, esempi, parole chiave e descrizione, con soglia normalizzata e taglio dei candidati deboli (sotto il 60% del migliore).
- **Hook**: usa anche gli ultimi 2 messaggi, ignora i comandi `/`, salta le skill già installate su disco.
- **Controllo qualità** (`tests/eval.py`): 23 richieste realistiche. Il workflow non pubblica l'indice se il primo posto scende sotto il 75% o i falsi allarmi superano il 25%.
