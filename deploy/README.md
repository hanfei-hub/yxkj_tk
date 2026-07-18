# Backend Server Deployment

## What Runs On The Server

The desktop app calls the backend through `TK_SELECTION_API_BASE_URL`.
After deployment the flow becomes:

```text
Desktop app -> https://YOUR_DOMAIN_OR_IP -> Nginx -> FastAPI backend -> Oxylabs / Doubao / AI MediaKit / Miaoshou
```

## Deploy From Windows

```powershell
powershell -ExecutionPolicy Bypass -File D:\yxkj_tk\deploy\deploy_backend.ps1 -HostName YOUR_SERVER_IP
```

The script uploads `backend/` and `deploy/` to `/opt/tk-selection` and runs the Linux installer.

## Configure Server Environment

On the server:

```bash
nano /etc/tk-selection/backend.env
```

Set at least:

```text
DATABASE_URL=mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/tk_selection?charset=utf8mb4
TK_SELECTION_SECRET_KEY=long-random-secret
AUTO_PUBLISH_ASSET_BASE_URL=https://YOUR_DOMAIN_OR_IP/static/auto_publish
```

Restart:

```bash
systemctl restart tk-selection-backend
systemctl status tk-selection-backend --no-pager
```

## Nginx

Copy `deploy/nginx-tk-selection.conf` to `/etc/nginx/sites-available/tk-selection`, replace `YOUR_DOMAIN_OR_IP`, then:

```bash
ln -sf /etc/nginx/sites-available/tk-selection /etc/nginx/sites-enabled/tk-selection
nginx -t
systemctl reload nginx
```

For HTTPS, use a domain and Certbot or your cloud provider certificate.

## Point Desktop To Server

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File D:\yxkj_tk\deploy\set_desktop_server_url.ps1 -ApiBaseUrl https://YOUR_DOMAIN_OR_IP
```

Restart the desktop app.

## Health Check

```powershell
Invoke-RestMethod https://YOUR_DOMAIN_OR_IP/api/health
```

Expected:

```json
{"ok": true, "service": "tk-selection-backend"}
```
