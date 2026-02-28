# Leitura Bíblica Diária (E-mail)

Este projeto envia por e-mail, diariamente, o **texto bíblico** correspondente à leitura do dia do seu plano.

## Como funciona
- `plan.csv` contém a data (`date`) e a leitura (`reading`) do dia.
- `bot.py`:
  1) pega a leitura do dia no CSV
  2) busca os capítulos via API (ABíbliaDigital)
  3) envia o e-mail via SMTP (Gmail)

## Arquivos
- `plan.csv` — plano com datas (início em 01/01/2026)
- `bot.py` — automação
- `requirements.txt` — dependências
- `.github/workflows/daily.yml` — agendamento diário (GitHub Actions)

## Variáveis/Secrets (GitHub)
- `EMAIL_USER` — seu Gmail
- `EMAIL_PASS` — senha de app do Gmail
- `EMAIL_TO` — destinatário
- `ABIBLIA_TOKEN` — token da ABíbliaDigital (recomendado)
