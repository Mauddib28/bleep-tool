# User mode (coming soon)

User mode will offer a **streamlined, opinionated workflow** aimed at field technicians and penetration testers who need quick answers without wading through every low-level detail.

Planned features:

| Feature | Status |
|---------|--------|
| Device discovery wizard | 🟡 in development |
| One-click GATT dump + HTML report | 🟡 in development |
| Simplified notification listener | 🟡 in development |
| Asset-of-Interest (AoI) checklist integration | 🔜 planned |

## Expected invocation

```bash
python -m bleep user   # alias for "-m interactive --profile user"
```

Until implementation lands you can achieve similar results via **interactive mode** with preloaded helper scripts – see `scripts/examples/*`. 