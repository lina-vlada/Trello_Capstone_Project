FROM nginx:alpine
COPY nginx/cloudrun/proxy_common.conf /etc/nginx/proxy_common.conf
COPY nginx/cloudrun/default.conf.template /etc/nginx/templates/default.conf.template
# Only substitute our variables so nginx's own $variables are left intact
ENV NGINX_ENVSUBST_FILTER=^(PORT|BACKEND_)
ENV PORT=8080
