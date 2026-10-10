# 🎁 Amigo Secreto

App web para fazer o sorteio do amigo secreto, sem ninguém (nem o organizador) ficar a saber os pares.

## Como funciona

Há duas áreas separadas:

**Gestão** (`/` + password). Na página inicial entras com a password (variável `token`) e vês todos os sorteios
guardados no servidor. Daí crias sorteios novos e geres os antigos.

1. **Criar** — escreve o nome do evento, o valor e os participantes (pode colar uma lista).
   Pessoas do mesmo **grupo** (casais, irmãos…) nunca se tiram umas às outras.
   Marca o **gestor** 👑: o email dele inclui também o link de gestão desse sorteio, que funciona sem password.
   Os nomes de quem já participou em sorteios anteriores aparecem como sugestão, e o email e o grupo são preenchidos
   sozinhos (também ao colar uma lista só com nomes).
2. **Enviar** — na página do sorteio, um clique envia a cada participante com email o seu **link pessoal**.
   O gestor recebe também o **link geral**, para o passar a quem não tem email.
   Se o sorteio tiver data (e hora, opcional), o email leva em anexo um **evento de calendário** (.ics),
   com lembrete na véspera.

**Participantes**:
- Com email: abrem o link pessoal e veem logo quem lhes calhou. No link geral, o nome deles fica bloqueado.
- Sem email: abrem o link geral, tocam no seu nome e escolhem um **PIN de 4 dígitos**. Noutro dispositivo, voltam a entrar com o PIN.

Todos tocam na prenda 🎁 para descobrir quem lhes calhou.
Os participantes nunca veem a área de gestão.

Na gestão vês quem já entrou e quem já viu, mas não os pares. Se alguém escolher o nome errado ou esquecer o PIN,
podes **libertar o nome**: o link antigo (pessoal ou com PIN) deixa de funcionar, e podes reenviar o email com um link novo. Após 5 PINs errados o nome fica bloqueado até ser libertado.
O sorteio pode ser refeito enquanto ninguém tiver visto o resultado.

**Lembranças.** No dia a seguir à data da troca (ou quando carregas em «Terminar sorteio»), o sorteio passa
para as **Lembranças**: deixa de ter links e envios, e mostra **quem ofereceu a quem**. Um sorteio terminado
à mão pode ser reaberto, se a data ainda não tiver passado.

## Correr

```bash
make dev                      # local, em http://localhost:8080 (password: o token do .env, ou "dev" se não houver)
make image                    # construir a imagem localmente
make test
```

## Deploy (Proxmox + Portainer + Cloudflare Tunnel)

```
GitHub (push para main) → GitHub Actions: testes + imagem ghcr.io/zbuh/secret_friend:latest
VM Docker/Portainer     → stack com essa imagem, porta 8080, volume com a base de dados
LXC cloudflared         → amigo.teudominio.pt → http://IP-da-VM:8080
```

1. **Imagem** — cada push para `main` publica `ghcr.io/zbuh/secret_friend:latest`.
   Na primeira vez, em GitHub → *Packages* → `secret_friend` → *Package settings*, muda a visibilidade para **Public**
   (assim o Portainer não precisa de credenciais).
2. **Portainer** — *Stacks → Add stack*, cola o `docker-compose.yaml` (ou usa *Repository* a apontar para este repo)
   e define em *Environment variables*: `token`, `base_url` (ex. `https://amigo.teudominio.pt`),
   `sender_mail` e `smtp_password`.
3. **Cloudflare** — em *Zero Trust → Networks → Tunnels →* o teu túnel *→ Public hostname*:
   subdomínio `amigo`, tipo **HTTP**, URL `IP-da-VM:8080`.
4. **Atualizar** — depois de um push para `main` (e de o GitHub Actions terminar), no Portainer abre a stack e faz
   *Update the stack* com **Re-pull image** ligado.
5. **Backups** — a base de dados está no volume `secret_friend_data` (um ficheiro SQLite). O backup da VM no Proxmox
   já a inclui.

## Configuração (variáveis de ambiente ou `.env`)

| Variável | Para quê |
|---|---|
| `token` | Password da área de gestão (criar e gerir sorteios). Sem ela, a área de gestão fica desligada. |
| `base_url` | URL público usado nos links (ex.: `https://amigo.exemplo.pt`). Por omissão usa o host do pedido. |
| `db_path` | Ficheiro SQLite (por omissão `data/secret_friend.db`; na imagem Docker, `/data/secret_friend.db`). |
| `FORWARDED_ALLOW_IPS` | IPs de proxies em que se confia para `X-Forwarded-*` (por omissão `*` na imagem). Podes pôr o IP do LXC do cloudflared. |
| `sender_mail`, `smtp_password` | Opcional. Ativa o envio dos links por email. Com Gmail, usa uma [palavra-passe de app](https://myaccount.google.com/apppasswords). |
| `smtp_server_domain_name`, `smtp_port` | Servidor SMTP (por omissão `smtp.gmail.com:587`). |

## Segurança

A área de gestão só funciona com a password (`token`) definida. Usa uma password forte: quem a souber vê e gere todos os sorteios.
O login fica guardado num cookie durante 30 dias. Mudar a password termina todas as sessões.

- Limites de pedidos por IP: tentativas de password (10/15 min), criar sorteios (30/hora), tentativas de PIN (20/10 min); envio de emails (5 envios/hora por sorteio).
- Após 5 PINs errados, o nome fica bloqueado até o organizador o libertar.
- Os links do organizador e de cada participante são aleatórios e impossíveis de adivinhar. As páginas não são indexadas nem guardadas em cache.
- Cabeçalhos de segurança (CSP, sem embeber noutros sites, sem `Referer`).

Os limites ficam em memória: reiniciar a app limpa-os. O cloudflared envia o IP real em `X-Forwarded-For`, e a imagem já confia nesse cabeçalho.
