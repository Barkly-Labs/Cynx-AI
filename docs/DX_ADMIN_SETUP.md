# CYN-X DX administrator access

CYN-X DX is the private research console for the single administrator. The ordinary companion at `/` stays available without a research-console login.

## First run

1. Start CYN-X on the local machine.
2. Open `http://127.0.0.1:8000/dx`.
3. Create the administrator password. It must be at least 12 characters and include a letter and a number.
4. Use the sign-out button when you finish working in DX.

The password is stored as a salted scrypt hash in the configured SQLite database. There is no public account-creation flow after setup. Sessions expire after 30 minutes without activity and at 12 hours maximum. Sign-in is limited to five failed attempts per 15 minutes per source address.

Administrative pages and APIs accept loopback traffic only by default. The `CYNX_ADMIN_ALLOW_REMOTE=1` setting explicitly changes that boundary and marks the session cookie secure. Only use it behind HTTPS, restrict network access at the firewall or reverse proxy, and configure the ASGI server to recognize HTTPS only from a trusted proxy. Do not expose the development server directly to the public internet.

## Model settings

Model Lab validates the selected model against the installed local Ollama model list. Activating a change saves a new version in the application database and applies it to new Ollama requests. Supported controls are context length, temperature, top-p, and repeat penalty. Omitted optional settings remain at Ollama's defaults. These settings change generation behavior; they do not retrain model weights.

Every activation uses an expected-version check. If another session changes the active version first, the stale save is rejected and the administrator must reload. Restoring a previous version creates a new version, preserving the history.
