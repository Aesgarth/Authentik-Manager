# Authentik Access Manager 🛡️

A modern, secure, and intuitive web application designed for self-hosters and homelab administrators running **[Authentik](https://goauthentik.io/)**.

It provides at-a-glance visibility into all your home services and users, an interactive permission matrix, automated application-to-group provisioning with **default-deny** security enforcement, and an invitation manager that pre-assigns service access to new users.

---

## ✨ Key Features

1. **Interactive Permission Matrix (Users × Applications)**
   - View all users, applications, and permissions in a single responsive grid.
   - Search by name, username, or email; filter by application categories or account status.
   - **Instant Mode vs. Staged Mode**: Toggle between instant updates or a staged review mode where you can inspect all changes before committing them to Authentik.
   - Protected superusers: Admins are clearly badged and protected against accidental lockout.

2. **Automated Application Group Provisioning & Security Enforcement**
   - In Authentik, an application without policy bindings is accessible to **any authenticated user**.
   - Authentik Access Manager highlights open/unprotected applications with a security warning badge.
   - **One-Click Provisioning**: Automatically generates dedicated access groups (e.g. `App - Jellyfin`) and attaches **Policy Bindings** directly to the application (`target=app, group=group`), locking down your home infrastructure to strict Role-Based Access Control (RBAC).

3. **Smart User Invitations with Pre-Configured Access**
   - Generate Authentik invitation links with pre-assigned application access.
   - Configurable token expiration (24h, 7 days, 30 days, or never) and single-use enforcement.
   - **Dual-Layer Auto-Assignment**:
     - *Layer 1 (Native Authentik Flow - Zero Latency)*: Drop-in Python Expression Policy snippet provided for your Authentik Enrollment Flow. Authentik automatically reads the invitation payload and assigns groups during registration.
     - *Layer 2 (Background Sync Worker - Zero Setup)*: The built-in background daemon continuously monitors Authentik for newly registered users and assigns the designated groups via the REST API automatically.

4. **WhatsApp Messaging Integration (via Baileys)**
   - Connect your WhatsApp account via an on-screen QR code (using the open-source Baileys library).
   - Enter a recipient's mobile number when creating an invite to automatically dispatch their personal setup link via WhatsApp.
   - Includes one-click `wa.me` fallback buttons for sharing directly via WhatsApp Web or mobile app.

5. **Multiple Authentication Methods (Including Full Authentik OIDC)**
   - **Authentik OpenID Connect (OIDC)**: Protect the manager using Authentik itself as the identity provider with OAuth2/OIDC. Enforces group membership (e.g., `authentik Admins`).
   - **Authentik Forward-Auth**: Compatible with Traefik / Nginx / Caddy using Authentik Outpost proxy headers (`X-authentik-username`, `X-authentik-groups`).
   - **Standalone Admin Password**: Quick setup for local networks or initial bootstrapping.
   - **Demo Mode**: Built-in mock data mode (`DEMO_MODE=true`) allows you to test and preview every feature safely before connecting your live Authentik instance.

5. **Local Audit Trail**
   - Every permission grant, revocation, app provisioning, and invite creation is recorded in a local SQLite audit database for full traceability.

---

## 🚀 Quick Start with Docker Compose

1. Clone this repository or copy `docker-compose.yml` and `.env.example`:

```bash
git clone https://github.com/your-username/authentik-manager.git
cd authentik-manager
cp .env.example .env
```

2. Edit `.env` with your Authentik details:

```env
AUTHENTIK_URL=https://authentik.yourdomain.local
AUTHENTIK_TOKEN=your_authentik_api_bearer_token_here
ADMIN_PASSWORD=your_secure_password
AUTH_METHOD=password # or 'oidc' / 'forward_auth' / 'none'
```

3. Launch the container:

```bash
docker compose up -d
```

4. Open `http://<your-server-ip>:8000` in your browser.

---

## 🔑 How to Generate an Authentik API Token

To allow the tool to manage users, groups, and policy bindings:

1. Log in to your Authentik Admin Interface.
2. Navigate to **Directory > Users**.
3. (Recommended) Create a Service Account (e.g. `svc-access-manager`) or select an administrator account.
4. If creating a service account, ensure it is added to the `authentik Admins` group.
5. In the user details view, navigate to the **Tokens & App passwords** tab.
6. Click **Create Token**:
   - **Identifier**: `access-manager-token`
   - **Intent**: `API Token`
   - **Expires**: Set according to your policy (or uncheck for permanent).
7. Copy the generated Key and paste it into `AUTHENTIK_TOKEN` in your `.env` file.

---

## 🔒 Setting up Full Authentik OIDC Login (SSO)

To protect this manager using Authentik as the identity provider:

1. In Authentik Admin, go to **Applications > Providers** and click **Create**:
   - **Type**: `OAuth2/OpenID Provider`
   - **Name**: `Authentik Access Manager Provider`
   - **Client type**: `Confidential`
   - **Redirect URI**: `https://manager.yourdomain.local/api/auth/oidc/callback`
   - Save and note down the **Client ID** and **Client Secret**.
2. Go to **Applications > Applications** and click **Create**:
   - **Name**: `Authentik Access Manager`
   - **Slug**: `authentik-manager`
   - **Provider**: Select the provider created above.
3. In your `.env` file for Authentik Access Manager, configure:
   ```env
   AUTH_METHOD=oidc
   OIDC_ISSUER_URL=https://authentik.yourdomain.local/application/o/authentik-manager/
   OIDC_CLIENT_ID=<your-client-id>
   OIDC_CLIENT_SECRET=<your-client-secret>
   OIDC_REDIRECT_URI=https://manager.yourdomain.local/api/auth/oidc/callback
   OIDC_ADMIN_GROUP=authentik Admins
   ```
4. Restart the container. Accessing the manager will now authenticate via Authentik Single Sign-On and enforce that only members of `OIDC_ADMIN_GROUP` can log in!

---

## 📱 WhatsApp Messaging Integration (via Baileys)

Authentik Access Manager integrates with **Baileys**, an open-source WhatsApp Web multi-device library, enabling you to deliver invitation links directly to family and friends over WhatsApp without paying for the WhatsApp Business API.

### 1. Linking your WhatsApp Account
1. Launch the single container (`docker compose up -d`). Both Authentik Access Manager and the internal WhatsApp Baileys bridge run seamlessly inside the same container under a managed process supervisor.
2. In the Authentik Access Manager web interface, click the **WhatsApp** / **Link WhatsApp** button in the top navigation bar.
3. Open WhatsApp on your phone:
   - Go to **Settings** (iOS) or **Three Dots Menu** (Android).
   - Tap **Linked Devices > Link a Device**.
   - Scan the QR code displayed on the screen.
4. Your account is now linked! Session credentials are encrypted and stored in the `/app/data/whatsapp_auth` folder in your single `manager-data` volume so you don't need to re-scan when restarting the container.

### 2. Sending Invitations via WhatsApp
- When creating an invite in the UI, enter the recipient's phone number (e.g. `+44 7123 456789` or `07123456789`).
- Check **Send invite link directly via WhatsApp**.
- The invite link is instantly dispatched with a friendly message explaining which services they will receive access to.
- Even if the WhatsApp bridge is offline, you can click the **Open in WhatsApp** button to launch WhatsApp Web or the app with a pre-filled invite message.

---

## ⚡ Zero-Latency In-Flow Group Assignment (Optional)

When creating invitation links, Authentik Access Manager includes an automatic background sync worker that polls Authentik and applies group memberships when invited users register.

If you prefer **instant, atomic assignment** handled directly by Authentik during registration:

1. In Authentik Admin, go to **Customization > Policies** and click **Create Policy**.
2. Select **Expression Policy** and name it `Assign Invitation Groups`.
3. Paste the following snippet:

```python
from authentik.core.models import Group

if "prompt_data" in request.context and "groups" in request.context.get("prompt_data", {}):
    target_groups = request.context["prompt_data"]["groups"]
    resolved_groups = []
    for g_id in target_groups:
        try:
            group = Group.objects.get(pk=g_id) if len(str(g_id)) == 36 else Group.objects.get(name=g_id)
            resolved_groups.append(group)
        except Group.DoesNotExist:
            ak_logger.warning(f"Group {g_id} not found during invitation enrollment")

    if resolved_groups:
        if "groups" not in request.context["flow_plan"].context:
            request.context["flow_plan"].context["groups"] = []
        request.context["flow_plan"].context["groups"].extend(resolved_groups)

return True
```

4. Go to **Flows & Stages > Flows**, edit your `default-enrollment-flow`, and under **Stage Bindings**, bind this policy to execute **before** the `default-user-write` stage.

---

## 🛠️ Local Development

### Prerequisites:
- Python 3.11+
- Node.js 20+

### Run Backend:
```bash
# In repository root
pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### Run Frontend:
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. Frontend API calls are automatically proxied to the backend at port 8000.

### Run Automated Tests:
```bash
# In repository root
py -3.12 -m pytest backend/tests/ -v -o pythonpath=backend
```

---

## 🛡️ Security Best Practices

- **Never expose the manager directly to the public internet** without a secure reverse proxy, VPN (e.g. Tailscale/Wireguard), or Authentik Forward-Auth outpost.
- Always use a strong `SECRET_KEY` and `ADMIN_PASSWORD`.
- Keep the `data/` volume persisted so audit logs and tracked invitations are preserved across updates.
