from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared instance: main.py registers it on app.state and wires the
# exception handler; routes.py applies @limiter.limit(...) to individual
# endpoints. Split out to avoid a routes.py <-> main.py import cycle.
limiter = Limiter(key_func=get_remote_address)
