worker = 4
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
keepalive = 65
graceful_timeout = 30
timeout = 120
accesslog = "-"
forwarded_allow_ips = "172.16.0.0/12, 10.0.0.0/8, 192.168.0.0/16"