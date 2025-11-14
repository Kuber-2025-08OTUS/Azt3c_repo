ARG ALPINE_VERSION=3.18

FROM alpine:${ALPINE_VERSION} as build
ARG NGINX=1.25.2

ENV NGINX_VERSION=${NGINX}

RUN apk update && apk add build-base pcre-dev libressl-dev zlib-dev wget ca-certificates && rm -rf /var/cache/apk/*

RUN wget -O nginx.tar.gz https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz \
    && tar -xzvf nginx.tar.gz \
    && cd nginx-${NGINX_VERSION} \
    &&  ./configure --prefix=/opt/nginx --sbin-path=/opt/nginx/sbin/nginx --conf-path=/opt/nginx/conf/nginx.conf --pid-path=/var/run/nginx/nginx.pid --lock-path=/var/run/nginx.lock --http-client-body-temp-path=/var/cache/nginx/client_temp --http-proxy-temp-path=/var/cache/nginx/proxy_temp --http-fastcgi-temp-path=/var/cache/nginx/fastcgi_temp --http-uwsgi-temp-path=/var/cache/nginx/uwsgi_temp --http-scgi-temp-path=/var/cache/nginx/scgi_temp --user=nginx --group=nginx --with-http_stub_status_module \
    && make -j$(nproc) \
    && make install

FROM alpine:${ALPINE_VERSION}

RUN apk --update add pcre libbz2 ca-certificates libressl && rm -rf /var/cache/apk/*

RUN adduser -h /etc/nginx -D -s /bin/sh nginx

COPY --from=build /opt/nginx /opt/nginx

ENV PATH="$PATH:/opt/nginx/sbin/"

#COPY nginx.conf /opt/nginx/conf/nginx.conf
#COPY conf.d /opt/nginx/conf.d

RUN mkdir -p /var/cache/nginx/client_temp \
             /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp \
             /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp \
             /opt/nginx/logs  \
    && chown -R nginx:nginx /var/cache/nginx \
    && mkdir -p /var/run/nginx && chown nginx:nginx /var/run/nginx \
    && chmod +rw /opt/nginx/conf && chmod +rwx /var/run/nginx \
    && chown -R  nginx:nginx /opt/nginx/logs  && chmod +rw -R /opt/nginx/logs 
EXPOSE 8000

USER nginx

CMD ["nginx"]