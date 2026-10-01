"""Load an Ahrefs key locally. Never print secret values or read other profiles."""
import os
from pathlib import Path


def load_key(environ=None):
    environ = os.environ if environ is None else environ
    key = environ.get('AHREFS_API_KEY', '')
    if key:
        return key
    home = environ.get('HERMES_HOME')
    if not home:
        raise ValueError('Missing active HERMES_HOME; open the skill in local Hermes for secure setup')
    path = Path(home) / '.env'
    if path.is_file():
        if os.name == 'posix' and path.stat().st_mode & 0o077:
            raise ValueError('Profile secret file permissions must be 0600')
        found = []
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line.startswith('export '):
                line = line[7:]
            if '=' not in line or line.startswith('#'):
                continue
            name, value = line.split('=', 1)
            if name.strip() != 'AHREFS_API_KEY':
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            found.append(value)
        if len(found) == 1 and found[0]:
            return found[0]
    raise ValueError('Missing or ambiguous AHREFS_API_KEY; load the skill for secure setup')
