#!/usr/bin/env python3
"""Measures suggestion quality on realistic prompts (phrased differently from the enrichment examples).
Usage: python3 tests/eval.py [index/index.json]   -> exits 1 if quality drops below the gate."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["SKILL_ADVISOR_INDEX_URL"] = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "index", "index.json")
sys.path.insert(0, os.path.join(ROOT, "skill", "scripts"))
from suggest import suggest  # noqa: E402

# (prompt, expected skill | tuple of acceptable skills | None = nothing should be suggested)
CASES = [
    ("mi serve un excel per tenere i conti delle spese mensili", "xlsx"),
    ("ho un csv sporco con righe duplicate, puoi sistemarlo", "xlsx"),
    ("preparami le slide per presentare il progetto al consiglio", "pptx"),
    ("devo fare un pitch per gli investitori la settimana prossima", "pptx"),
    ("scrivimi un contratto di collaborazione da mandare in word", "docx"),
    ("apri questo file .docx e correggi gli errori", "docx"),
    ("devo unire tre pdf in un unico file", "pdf"),
    ("tira fuori le tabelle da questo pdf scansionato", "pdf"),
    ("voglio verificare con playwright che il login della mia app locale funzioni", "webapp-testing"),
    ("fai dei test automatici sul mio sito in sviluppo e cattura screenshot", "webapp-testing"),
    ("crea una locandina per la festa di halloween da stampare", "canvas-design"),
    ("voglio un server mcp per collegare claude al mio gestionale", "mcp-builder"),
    ("come integro le api di claude nel mio backend node", "claude-api"),
    ("scriviamo una proposta strutturata per il nuovo cliente", "doc-coauthoring"),
    ("prepara l'aggiornamento settimanale per la direzione", "internal-comms"),
    ("voglio creare una nuova skill per claude che gestisca le email", "skill-creator"),
    ("la landing page sembra un template, rendila più curata", "frontend-design"),
    ("una gif animata da mettere nel canale slack del team", "slack-gif-creator"),
    ("disegno generativo con particelle in p5js", "algorithmic-art"),
    ("ciao come stai", None),
    ("che tempo fa domani a roma", None),
    ("grazie mille, perfetto così", None),
    ("riassumimi questo articolo in tre punti", None),
    ("ok procedi pure", None),
    ("puoi spiegarmi meglio il punto due", None),
    ("quanto fa 15 per 23", None),
    ("traduci questo testo in inglese", None),
    ("perché il cielo è blu", None),
    ("devo pubblicare il sito su vercel", ("deploy-to-vercel", "vercel-deploy")),
    ("aggiungi i pagamenti con stripe al mio sito", ("stripe-implementation-planner", "stripe-best-practices")),
    ("crea un database postgres su supabase con le tabelle utenti", ("supabase-postgres-best-practices", "supabase")),
    # other languages (phrased differently from the enrichment examples)
    ("necesito una hoja de cálculo para controlar los gastos de casa", "xlsx"),
    ("prépare une présentation pour le comité de direction", "pptx"),
    ("ich muss drei PDF-Dateien zu einer zusammenfügen", "pdf"),
    ("preciso de um cartaz para imprimir para a festa da escola", "canvas-design"),
    ("quiero cobrar con stripe en mi tienda online", ("stripe-implementation-planner", "stripe-best-practices")),
    ("écris une réponse polie à ce client mécontent", "draft-response"),
    ("Zahlungserinnerung für offene Rechnungen an Kunden schreiben", "invoice-chase"),
    ("revisa las cláusulas de este contrato de proveedor", "review-contract"),
    ("fammi un preventivo per il cliente dopo la chiamata di oggi", "proposal-builder"),
    ("faz um gráfico de barras com as vendas do trimestre", "create-viz"),
    ("hola, ¿qué tal?", None),
    ("merci beaucoup, c'est parfait", None),
    ("wie spät ist es in New York", None),
    ("obrigado, pode continuar", None),
    ("secondo te è necessario?", None),
]


def main():
    hit1 = hit3 = fp = 0
    pos = sum(1 for _, e in CASES if e)
    neg = len(CASES) - pos
    for prompt, exp in CASES:
        res = [s["name"] for _, s in suggest(prompt)]
        good = set(exp) if isinstance(exp, tuple) else {exp}
        ok = bool(good & set(res[:1])) if exp else not res
        if exp:
            hit1 += bool(good & set(res[:1]))
            hit3 += bool(good & set(res[:3]))
        else:
            fp += bool(res)
        print(f"{'OK ' if ok else 'NO '} {prompt[:60]:<60} -> {res}  (atteso: {exp})")
    p1, p3, fpr = hit1 / pos, hit3 / pos, fp / neg
    print(f"\nprimo posto: {p1:.0%} | tra i primi 3: {p3:.0%} | falsi allarmi: {fpr:.0%}")
    sys.exit(0 if p1 >= 0.75 and fpr <= 0.25 else 1)


if __name__ == "__main__":
    main()
