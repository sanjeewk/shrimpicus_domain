# Gunicorn configuration file for shrimpicus web app

import multiprocessing

# Bind to all interfaces on port 8000
bind = "0.0.0.0:8000"

# Number of worker processes
# Rule of thumb: (2 x num_cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1

# Worker class - sync is fine for our use case
worker_class = "sync"

# Maximum requests per worker before restart (helps prevent memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Timeout for requests (in seconds)
timeout = 30

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"

# Process naming
proc_name = "shrimpicus-web"

# Preload app for better performance
preload_app = True

# Graceful timeout
graceful_timeout = 30
