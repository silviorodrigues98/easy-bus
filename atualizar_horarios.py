#!/usr/bin/env python3
"""
Atualiza os horários do app "Meu Ônibus" com os dados do site da Floramar.

Uso (na pasta onde está o index.html do app):
    python atualizar_horarios.py                 -> atualiza index.html
    python atualizar_horarios.py meu_app.html    -> atualiza outro arquivo
    python atualizar_horarios.py --testar        -> só baixa e mostra o resumo, não grava nada

O que ele faz:
  1. Baixa todas as linhas e horários de floramar.com.br/linhas.
  2. Confere se os dados fazem sentido (se o site mudar de formato, ele para sem estragar o app).
  3. Mostra o que mudou em relação ao app atual.
  4. Guarda uma cópia de segurança do arquivo antigo e grava os novos horários.

Depois, é só subir o arquivo atualizado de novo no Netlify.
Precisa apenas do Python 3 (não usa nenhuma biblioteca extra).
"""
import argparse
import datetime as dt
import html
import http.cookiejar
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request

SITE = "https://floramar.com.br"
MAX_ID = 300            # procura linhas com id de 1 até aqui
PARAR_APOS_VAZIOS = 60  # para de procurar depois de tantos ids vazios seguidos
PAUSA = 0.3             # segundos entre pedidos, para não sobrecarregar o site

DIAS = {"semana": "Úteis", "sabado": "Sáb", "domingo": "Dom"}


# ----------------------------------------------------------------- download
def criar_cliente(base):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "Mozilla/5.0 (atualizador de horarios)"),
                         ("Referer", base + "/linhas")]
    try:
        opener.open(base + "/linhas", timeout=30).read()  # pega cookies de sessão, se houver
    except Exception as e:
        sys.exit(f"Não consegui abrir {base}/linhas: {e}")
    return opener


def baixar_linha(opener, base, id_):
    dados = urllib.parse.urlencode({"id": id_}).encode()
    for tentativa in range(3):
        try:
            with opener.open(base + "/linhas_detalhes", data=dados, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if tentativa == 2:
                print(f"  ! falhou id {id_}: {e}")
                return ""
            time.sleep(2)


# ----------------------------------------------------------------- leitura do HTML
def texto(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def ler_pagina(pag):
    m = re.search(r"<title>\s*Linha\s+(\S+)\s+-\s+(.*?)\s*</title>", pag, re.S | re.I)
    if not m:
        return None
    codigo, nome = texto(m.group(1)), texto(m.group(2))

    def campo(rotulo):
        m = re.search(r">\s*" + rotulo + r"\s*</div>\s*<div[^>]*>(.*?)</div>", pag, re.S)
        return texto(m.group(1)) if m else ""

    origem, destino = campo("Origem"), campo("Destino")

    m = re.search(r'<section[^>]*id="horarios".*?(?=<section|\Z)', pag, re.S)
    quadros = []
    if m:
        secao = m.group(0)
        for card in re.split(r'<div class="card[ "]', secao)[1:]:
            partes = card.split("card-body", 1)
            if len(partes) < 2:
                continue
            badge = re.search(r'<span class="badge[^"]*">(.*?)</span>', partes[0], re.S)
            if not badge:
                continue
            quadro = {"dias": texto(badge.group(1)), "grupos": []}
            tipo, sentido, atual = None, None, None
            for t in re.finditer(r'<h3[^>]*>(.*?)</h3>'
                                 r'|<p class="[^"]*fw-semibold[^"]*">(.*?)</p>'
                                 r'|<span class="[^"]*badge-horario[^"]*">(.*?)</span>', partes[1], re.S):
                if t.group(1) is not None:
                    tipo, sentido, atual = texto(t.group(1)), None, None
                elif t.group(2) is not None:
                    sentido, atual = texto(t.group(2)), None
                else:
                    h = texto(t.group(3))
                    if not re.fullmatch(r"\d{2}:\d{2}", h):
                        continue
                    if atual is None:
                        atual = {"tipo": tipo, "sentido": sentido, "horarios": []}
                        quadro["grupos"].append(atual)
                    atual["horarios"].append(h)
            if quadro["grupos"]:
                quadros.append(quadro)
    return {"codigo": codigo, "nome": nome, "origem": origem, "destino": destino, "quadros": quadros}


# ----------------------------------------------------------------- montagem dos dados do app
PEQUENAS = {"da", "de", "do", "das", "dos", "e"}


def tc(s):
    """ESTAÇÃO CENTRAL -> Estação Central"""
    palavras = s.lower().split(" ")
    out = []
    for i, p in enumerate(palavras):
        if i and p in PEQUENAS:
            out.append(p)
        else:
            out.append(re.sub(r"(^|[(./-])([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), p))
    return " ".join(out).replace("Puc", "PUC")


def eh_principal(g):
    s = (g["sentido"] or "").lower()
    return g["tipo"] == "Horários principais" and (not s or s == "partindo do centro")


def rotulo(g):
    lab = []
    if g["tipo"] and g["tipo"] != "Horários principais":
        lab.append(g["tipo"])
    if g["sentido"] and g["sentido"].lower() != "partindo do centro":
        lab.append(g["sentido"])
    return " · ".join(lab)


def eh_do_bairro(r):
    return bool(re.search(r"bairro → centro|começa no bairro|in[ií]cio no bairro", r, re.I))


def montar(linhas_site):
    usados = {}
    for l in linhas_site:
        usados[l["codigo"]] = usados.get(l["codigo"], 0) + 1

    app = []
    for l in linhas_site:
        id_ = l["codigo"]
        if usados[l["codigo"]] > 1:  # mesmo código com sentidos diferentes (ex.: N23)
            m = re.search(r"SENTIDO\s+([^)]+)", l["nome"], re.I)
            sufixo = "".join(p[0] for p in re.split(r"[\s.]+", m.group(1)) if p) if m else str(len(app))
            id_ = f"{l['codigo']}_{sufixo.upper()}"

        horarios, observacoes = {}, {}
        for dia, chave in DIAS.items():
            todos, obs = set(), {}
            for q in l["quadros"]:
                if chave not in q["dias"]:
                    continue
                principais = {h for g in q["grupos"] if eh_principal(g) for h in g["horarios"]}
                for g in q["grupos"]:
                    r = rotulo(g)
                    for h in g["horarios"]:
                        todos.add(h)
                        if not r:
                            continue
                        if h in principais:  # o mesmo horário também sai do ponto principal
                            if eh_do_bairro(r):
                                r2 = "Neste horário também sai um" + (" extra" if "extra" in r.lower() else "") + " do bairro"
                            elif r.lower().startswith("via "):
                                r2 = "Neste horário também sai um " + r[0].lower() + r[1:]
                            else:
                                r2 = r
                            obs.setdefault(h, []).append(r2)
                        else:
                            obs.setdefault(h, []).append(r)
            horarios[dia] = sorted(todos)
            obs = {h: " + ".join(dict.fromkeys(v)) for h, v in sorted(obs.items())}
            if obs:
                observacoes[dia] = obs

        partes = [p.strip() for p in l["nome"].split("/")]
        extremos = {l["origem"].upper(), l["destino"].upper()}
        via = " / ".join(tc(p) for p in partes[1:]
                         if not re.search(r"EST(AÇÃO|\.)?\s*CENTRAL", p) and p.upper() not in extremos)

        # Se o site informa pontos de saída ("Partindo da Estação Sul", "Saída PUC"...) e a origem
        # cadastrada não é nenhum deles, usa o ponto com mais horários como origem.
        origem = tc(l["origem"] or "Estação Central")
        pontos = {}
        for q in l["quadros"]:
            for g in q["grupos"]:
                m = re.match(r"(?:Saindo|Partindo)\s+d[ao]\s+(.+)|Saída\s+(.+)", g["sentido"] or "", re.I)
                if m:
                    p = (m.group(1) or m.group(2)).strip()
                    if not re.search(r"centro", p, re.I):
                        pontos[p] = pontos.get(p, 0) + len(g["horarios"])
        if pontos and origem.lower() not in {p.lower() for p in pontos}:
            origem = max(pontos, key=pontos.get)

        item = {"id": id_, "codigo": l["codigo"],
                "origem": origem,
                "via": via,
                "destino": tc(l["nome"]) if usados[l["codigo"]] > 1 else tc(l["destino"] or l["nome"]),
                "nomeDisplay": f"{l['codigo']} - {tc(l['nome'])}",
                "horarios": horarios}
        if observacoes:
            item["observacoes"] = observacoes
        app.append(item)
    return app


# ----------------------------------------------------------------- app (HTML)
PADRAO_DADOS = re.compile(r"(const LINHAS = )(\[.*?\n    \]);", re.S)


def dados_atuais(html_app):
    m = PADRAO_DADOS.search(html_app)
    if not m:
        sys.exit("Não achei os dados ('const LINHAS = [...]') dentro do arquivo do app.")
    try:
        return json.loads(m.group(2))
    except json.JSONDecodeError:
        return None  # formato antigo; segue sem comparar


def resumo(antigo, novo):
    if antigo is None:
        print("(não deu para comparar com a versão anterior)")
        return
    a = {l["id"]: l for l in antigo}
    n = {l["id"]: l for l in novo}
    for i in n.keys() - a.keys():
        print(f"  + linha nova: {n[i]['nomeDisplay']}")
    for i in a.keys() - n.keys():
        print(f"  - linha removida do site: {a[i]['nomeDisplay']}")
    mudou = 0
    for i in n.keys() & a.keys():
        for dia in DIAS:
            x, y = set(a[i]["horarios"].get(dia, [])), set(n[i]["horarios"].get(dia, []))
            if x != y:
                mudou += 1
                ent, sai = sorted(y - x), sorted(x - y)
                print(f"  * {n[i]['codigo']} ({dia}): " +
                      (f"novos {', '.join(ent)}" if ent else "") +
                      ("; " if ent and sai else "") +
                      (f"saíram {', '.join(sai)}" if sai else ""))
    if not mudou and n.keys() == a.keys():
        print("  Nenhum horário mudou.")


def main():
    ap = argparse.ArgumentParser(description="Atualiza os horários do app com o site da Floramar.")
    ap.add_argument("arquivo", nargs="?", default="index.html", help="arquivo HTML do app (padrão: index.html)")
    ap.add_argument("--testar", action="store_true", help="só mostra o resumo, não grava")
    ap.add_argument("--site", default=SITE, help=argparse.SUPPRESS)
    args = ap.parse_args()

    try:
        html_app = open(args.arquivo, encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"Não consegui abrir o arquivo do app: {e}")
    antigo = dados_atuais(html_app)

    print(f"Baixando linhas de {args.site} ...")
    opener = criar_cliente(args.site)
    linhas, vazios, id_ = [], 0, 0
    while id_ < MAX_ID and vazios < PARAR_APOS_VAZIOS:
        id_ += 1
        l = ler_pagina(baixar_linha(opener, args.site, id_))
        if l:
            vazios = 0
            linhas.append(l)
            n = sum(len(g["horarios"]) for q in l["quadros"] for g in q["grupos"])
            print(f"  {l['codigo']:6} {l['nome'][:50]:50} {n:4} horários")
        else:
            vazios += 1
        time.sleep(PAUSA)

    # Conferências de segurança: se algo parecer errado, não grava nada.
    problemas = []
    if len(linhas) < 10:
        problemas.append(f"só encontrei {len(linhas)} linhas")
    if antigo and len(linhas) < 0.7 * len(antigo):
        problemas.append(f"encontrei {len(linhas)} linhas, mas o app tinha {len(antigo)}")
    sem = [l["codigo"] for l in linhas if not l["quadros"]]
    if len(sem) > len(linhas) * 0.2:
        problemas.append(f"{len(sem)} linhas vieram sem horários ({', '.join(sem[:8])}...)")
    if problemas:
        print("\nPAREI SEM GRAVAR: o site pode ter mudado de formato.")
        for p in problemas:
            print("  - " + p)
        sys.exit(1)
    if sem:
        print(f"\nAtenção: estas linhas vieram sem horários: {', '.join(sem)}")

    novo = montar(linhas)
    print(f"\n{len(novo)} linhas lidas. O que mudou em relação ao app:")
    resumo(antigo, novo)

    if args.testar:
        print("\nModo teste: nada foi gravado.")
        return

    hoje = dt.date.today()
    copia = re.sub(r"(\.html?)?$", f".backup-{hoje:%Y%m%d}.html", args.arquivo, count=1)
    shutil.copyfile(args.arquivo, copia)

    js = "[\n" + ",\n".join("      " + json.dumps(l, ensure_ascii=False) for l in novo) + "\n    ]"
    novo_html = PADRAO_DADOS.sub(lambda m: m.group(1) + js + ";", html_app, count=1)
    novo_html = re.sub(r"(conferidos no site floramar\.com\.br em )\d{2}/\d{2}/\d{4}",
                       lambda m: m.group(1) + f"{hoje:%d/%m/%Y}", novo_html)
    with open(args.arquivo, "w", encoding="utf-8") as f:
        f.write(novo_html)
    with open("horarios_floramar.json", "w", encoding="utf-8") as f:
        json.dump(linhas, f, ensure_ascii=False, indent=2)

    print(f"\nPronto! {args.arquivo} atualizado.")
    print(f"Cópia da versão anterior: {copia}")
    print("Agora suba o arquivo de novo no Netlify para o celular pegar a versão nova.")


if __name__ == "__main__":
    main()
