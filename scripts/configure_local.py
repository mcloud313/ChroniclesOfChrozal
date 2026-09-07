"""Create a private local configuration once, using only the Python standard library."""
import os
import secrets
from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'.env'
password=secrets.token_hex(24)
content=(root/'.env.example').read_text().replace('replace-with-a-long-random-password',password)
try:
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
except FileExistsError:
    raise SystemExit('Existing .env retained. Edit it explicitly if you intend to change configuration.')
with os.fdopen(fd,'w') as stream:stream.write(content)
print('Local configuration created with a generated database password. Browser origin: http://localhost:8000')
