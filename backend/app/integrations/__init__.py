"""
Real platform clients: the only files that talk to Meta (WhatsApp, Facebook),
Instagram and Google. Each function = one call to that company's API.
They're only used for connections in "real" mode; mock connections never
call out (see services/connection_service.py).
"""
