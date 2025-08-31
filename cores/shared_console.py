# file: shared_console.py
from rich.console import Console

# Inilah satu-satunya objek Console yang akan digunakan oleh seluruh aplikasi.
console = Console(log_path=True,log_time=True)
