import json, os
from src.notify.discord import DiscordNotifier

with open('data/runs/2026-04-08_193537/decision_shortlist.json') as f:
    data = json.load(f)

opps = data['opportunities']
print(f'Sending {len(opps)} opportunities...')
result = DiscordNotifier().send(opps, '2026-04-08_193537-resend')
print(f'Discord send result: {result}')
