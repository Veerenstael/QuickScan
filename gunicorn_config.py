# Gunicorn configuratie voor Veerenstael QuickScan
workers = 2
worker_class = "sync"
timeout = 300  # 2 minuten i.p.v. 30 seconden
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
loglevel = "info"
