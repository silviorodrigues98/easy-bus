# Meu Ônibus

App simples e leve para consultar os horários das linhas de ônibus da **Floramar** direto no celular. Tudo em um único arquivo HTML, sem dependências e sem servidor.

Feito pensando no meu pai idoso, para facilitar e simplificar a visualização dos horários: tela limpa, fonte grande e poucos toques para chegar ao que interessa.

> App não oficial. Os horários são conferidos no site [floramar.com.br](https://floramar.com.br).

## Funcionalidades

- Escolha da linha com busca por nome do bairro ou número (ex.: `rosalia`, `kennedy`, `225`)
- Contagem regressiva para os próximos embarques
- Lista completa dos horários do dia (semana, sábado e domingo)
- Linhas recentes e linha salva automaticamente (funciona offline via `localStorage`)
- Ajuste de fonte grande e botões com alvos de toque amplos (fácil acesso)

## Estrutura do projeto

| Arquivo | Descrição |
|---|---|
| `index.html` | O app inteiro (HTML + CSS + JavaScript + dados dos horários) |
| `atualizar_horarios.py` | Script que baixa os horários atualizados do site da Floramar |
| `atualizar.bat` | Atalho no Windows que roda o script acima |

## Como usar

Basta abrir o `index.html` em qualquer navegador. Não é preciso instalar nada.

## Atualizar os horários

Requer apenas Python 3 (sem bibliotecas extras). Rode na pasta do app:

```bash
python atualizar_horarios.py            # atualiza o index.html
python atualizar_horarios.py --testar   # só baixa e mostra o resumo, sem gravar
```

No Windows, também é possível dar dois cliques em `atualizar.bat`.

O script:

1. Baixa todas as linhas e horários do site da Floramar
2. Valida os dados (para sem caso o formato do site mude, sem estragar o app)
3. Mostra o que mudou em relação à versão atual
4. Salva uma cópia de segurança do arquivo antigo e grava os novos horários

Depois, é só subir o `index.html` atualizado.

## Publicação

O app é um site estático: pode ser publicado no [Netlify](https://www.netlify.com), GitHub Pages ou qualquer hospedagem estática — basta enviar o `index.html`.
