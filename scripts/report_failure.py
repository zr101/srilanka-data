"""Maintain one issue per dataset; unchanged failures generate no comments."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

name = sys.argv[1]
repo = os.environ['GITHUB_REPOSITORY']
path = Path('data_checkout/data') / name / 'status.json'
status = json.loads(path.read_text()) if path.exists() else {}
message = status.get('message', 'Workflow setup, tests, or publication failed; inspect Actions logs.')
# Keep stable failure text in the body; run timestamps would cause daily updates.
body = f"{message}\n\nLatest publication: {status.get('publication_date', 'unknown')}\n\nRuns: https://github.com/{repo}/actions/workflows/pipeline.yml\n"
title = f'Pipeline failure: {name}'
issues = json.loads(subprocess.check_output(['gh', 'issue', 'list', '--repo', repo, '--state', 'open', '--search', title + ' in:title', '--json', 'number,title,body'], text=True))
existing = next((i for i in issues if i['title'] == title), None)
if existing and re.sub(r'\d{8}', '<edition>', existing['body']).strip() == re.sub(r'\d{8}', '<edition>', body).strip():
    print('Unchanged failure; existing issue retained without another notification')
    sys.exit(0)
with tempfile.NamedTemporaryFile(mode='w', suffix='.md') as temp:
    temp.write(body); temp.flush()
    args = ['gh', 'issue', 'edit', str(existing['number'])] if existing else ['gh', 'issue', 'create', '--title', title]
    subprocess.run(args + ['--repo', repo, '--body-file', temp.name], check=True)
