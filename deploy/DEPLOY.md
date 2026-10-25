# Deploy to a VPS (Ubuntu 24.04)

Needs: a VPS with 1 vCPU / 1 GB RAM (enough for one or several bots), SSH access.

## 1. Server setup (once)

```bash
ssh root@SERVER_IP
apt update && apt upgrade -y
adduser bot && usermod -aG sudo bot
# Docker (official script)
curl -fsSL https://get.docker.com | sh
usermod -aG docker bot
su - bot
```

## 2. Get the bot

```bash
git clone https://github.com/zhangir777/telegram-booking-bot.git
cd telegram-booking-bot
cp .env.example .env
nano .env            # BOT_TOKEN=..., ADMIN_IDS=[your_id]
nano business.yaml   # name, address, phone, FAQ of the client
```

## 3. Start

```bash
docker compose up -d --build
docker compose logs -f bot        # Ctrl+C to exit logs
docker compose run --rm bot uv run --no-sync seed-demo   # only for the demo bot!
```

`restart: unless-stopped` restarts the bot after crashes and server reboots.

## 4. Daily SQLite backup

```bash
mkdir -p ~/backups
crontab -e
```
Add the line (03:00 every day, keep 14 days):
```
0 3 * * * cd ~/telegram-booking-bot && sqlite3 data/bot.db ".backup '/home/bot/backups/bot-$(date +\%F).db'" && find ~/backups -name 'bot-*.db' -mtime +14 -delete
```
(`sudo apt install sqlite3` if missing.) Copy backups off the server from time to time:
`scp bot@SERVER_IP:backups/*.db .`

## 5. Update the bot

```bash
cd ~/telegram-booking-bot
git pull
docker compose up -d --build
```

## Without Docker (systemd)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --no-dev
sudo cp deploy/booking-bot.service /etc/systemd/system/
sudo systemctl enable --now booking-bot
journalctl -u booking-bot -f
```
