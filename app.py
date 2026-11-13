"""Vercel ASGI entrypoint. Importing/building does not require secrets or database access."""
from pathlib import Path
from orange_incident.hosted import create_entrypoint

app=create_entrypoint(Path(__file__).resolve().parent)
