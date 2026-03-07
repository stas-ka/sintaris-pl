"""
Run this ONCE on Windows to authorize Gmail access.
A browser window will open — log in as stas.ulmer@gmail.com and allow access.
The resulting gmail_token.json will be copied to the Pi automatically.
"""
import os, subprocess
from google_auth_oauthlib.flow import InstalledAppFlow

CREDS_FILE  = os.path.join(os.path.dirname(__file__),
              'client_secret_274246213880-25io6nlau004hpaoohke0mdmdvcje53e.apps.googleusercontent.com.json')
TOKEN_FILE  = os.path.join(os.path.dirname(__file__), 'gmail_token.json')
SCOPES      = ['https://www.googleapis.com/auth/gmail.readonly']

flow  = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
creds = flow.run_local_server(port=8080, open_browser=True)

with open(TOKEN_FILE, 'w') as f:
    f.write(creds.to_json())

print(f'\nToken saved to: {TOKEN_FILE}')
print('Copying to Pi...')

def _load_hostpwd():
    """Load Pi SSH password from HOSTPWD env var or from .env file (gitignored)."""
    pwd = os.environ.get('HOSTPWD', '')
    if not pwd:
        env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
        if os.path.exists(env_file):
            for line in open(env_file):
                if line.startswith('HOSTPWD='):
                    pwd = line.strip().split('=', 1)[1]
                    break
    return pwd

result = subprocess.run([
    r'C:\Program Files\PuTTY\pscp.exe',
    '-pw', _load_hostpwd(),
    TOKEN_FILE,
    'stas@OpenClawPI:/home/stas/.picoclaw/gmail_token.json'
], capture_output=True, text=True)

if result.returncode == 0:
    print('Copied to Pi OK: /home/stas/.picoclaw/gmail_token.json')
else:
    print('pscp error:', result.stderr)
    print('Copy manually:\n  pscp -pw "$HOSTPWD" .credentials\\gmail_token.json stas@OpenClawPI:/home/stas/.picoclaw/gmail_token.json')
