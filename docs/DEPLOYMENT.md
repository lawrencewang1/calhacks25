# Deployment Guide

This guide covers deploying the Multiplayer AI Chat application to production.

## Prerequisites

- Linux server (Ubuntu 20.04+ recommended)
- Python 3.8 or higher
- Nginx (for reverse proxy)
- SSL certificate (Let's Encrypt recommended)
- Domain name

## Production Checklist

Before deploying to production, ensure you've completed these tasks:

### Security
- [ ] Generate strong `JWT_SECRET_KEY` (use `openssl rand -hex 32`)
- [ ] Set `FLASK_ENV=production`
- [ ] Configure CORS with specific origins (no wildcards)
- [ ] Enable HTTPS/SSL
- [ ] Set secure session cookies
- [ ] Implement rate limiting
- [ ] Add input validation and sanitization
- [ ] Configure content moderation

### Configuration
- [ ] Set up environment variables in `.env`
- [ ] Configure database (consider PostgreSQL for production)
- [ ] Set up logging
- [ ] Configure LLM API credentials
- [ ] Set appropriate max token limits

### Monitoring
- [ ] Set up error logging
- [ ] Configure application monitoring
- [ ] Set up alerts for errors
- [ ] Monitor resource usage

## Deployment Steps

### 1. Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install python3.10 python3.10-venv python3-pip nginx -y

# Install certbot for SSL
sudo apt install certbot python3-certbot-nginx -y
```

### 2. Application Setup

```bash
# Clone repository
cd /var/www
sudo git clone <your-repo-url> chat-app
cd chat-app

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn eventlet  # Production server
```

### 3. Environment Configuration

Create production `.env` file:

```bash
sudo nano .env
```

```env
# Flask Configuration
FLASK_ENV=production
JWT_SECRET_KEY=<generate-with-openssl-rand-hex-32>
PORT=5000

# Database (use PostgreSQL in production)
SQLALCHEMY_DATABASE_URI=postgresql://user:pass@localhost/chatdb

# LLM Configuration
LLM_API_URL=https://janitorai.com/hackathon/completions
LLM_AUTH_TOKEN=your-token-here
MAX_OUT_TOKENS=400

# CORS (your domain)
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Security
ALLOW_GUESTS=false
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
```

### 4. Database Migration

```bash
# If using PostgreSQL
sudo apt install postgresql postgresql-contrib
sudo -u postgres createuser chatuser
sudo -u postgres createdb chatdb
sudo -u postgres psql -c "ALTER USER chatuser WITH PASSWORD 'securepassword';"

# Initialize database
python run.py  # Will create tables automatically
```

### 5. Create Systemd Service

Create service file:

```bash
sudo nano /etc/systemd/system/chat-app.service
```

```ini
[Unit]
Description=Multiplayer AI Chat Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/chat-app
Environment="PATH=/var/www/chat-app/.venv/bin"
ExecStart=/var/www/chat-app/.venv/bin/gunicorn \
    --worker-class eventlet \
    -w 1 \
    --bind 127.0.0.1:5000 \
    run:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start service:

```bash
sudo systemctl enable chat-app
sudo systemctl start chat-app
sudo systemctl status chat-app
```

### 6. Nginx Configuration

Create Nginx config:

```bash
sudo nano /etc/nginx/sites-available/chat-app
```

```nginx
upstream chat_app {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Static files
    location /static {
        alias /var/www/chat-app/frontend/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # WebSocket support
    location /socket.io {
        proxy_pass http://chat_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache_bypass $http_upgrade;
    }

    # Application
    location / {
        proxy_pass http://chat_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/chat-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7. SSL Certificate

```bash
# Get SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

### 8. Firewall Configuration

```bash
# Allow HTTP, HTTPS, and SSH
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## Monitoring and Maintenance

### View Logs

```bash
# Application logs
sudo journalctl -u chat-app -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Restart Services

```bash
# Restart application
sudo systemctl restart chat-app

# Restart Nginx
sudo systemctl restart nginx
```

### Update Application

```bash
cd /var/www/chat-app
sudo git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart chat-app
```

## Scaling Considerations

### Horizontal Scaling
- Use Redis for session storage
- Implement message queue for AI processing
- Use load balancer for multiple app instances
- Consider using managed database (RDS, etc.)

### Performance Optimization
- Enable gzip compression in Nginx
- Use CDN for static assets
- Implement caching strategies
- Optimize database queries
- Consider WebSocket sticky sessions

### Database
- Use PostgreSQL instead of SQLite
- Set up regular backups
- Configure connection pooling
- Add database indexes
- Monitor query performance

## Troubleshooting

### Application won't start
- Check logs: `sudo journalctl -u chat-app -n 50`
- Verify environment variables
- Check file permissions
- Ensure dependencies are installed

### WebSocket connection fails
- Check Nginx WebSocket configuration
- Verify CORS settings
- Check firewall rules
- Review SSL certificate

### Database connection errors
- Verify DATABASE_URI in .env
- Check database service status
- Verify credentials
- Check connection limits

## Backup Strategy

```bash
# Database backup (PostgreSQL)
pg_dump chatdb > backup_$(date +%Y%m%d).sql

# Application backup
tar -czf chat-app-backup_$(date +%Y%m%d).tar.gz /var/www/chat-app
```

## Support

For issues or questions:
- Check application logs
- Review this documentation
- Open an issue on GitHub
- Contact system administrator
