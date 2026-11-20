set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

test:
    python -B -m unittest discover -s tests -p "test_*.py" -v
