# Poison shadow of the stdlib json module; proves the source root is never on sys.path.
raise RuntimeError("source-root json.py must never be imported")
