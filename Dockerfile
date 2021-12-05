FROM python:3.9-alpine
LABEL maintainer="operations@vico-research.com"
LABEL Description="zabbix-kubernetes - efficent kubernetes monitoring for zabbix"

MAINTAINER operations@vico-research.com

ENV K8S_API_HOST ""
ENV K8S_API_TOKEN ""
ENV ZABBIX_SERVER "zabbix"
ENV ZABBIX_HOST "k8s"
ENV CRYPTOGRAPHY_DONT_BUILD_RUST "1"

COPY --chown=nobody:users requirements.txt /app/requirements.txt

RUN  apk update && \
       apk add build-base libffi-dev libffi openssl-dev bash screen && \
       pip install --upgrade pip && \
       pip install -r /app/requirements.txt && \
       apk upgrade --update-cache --available && \
       apk del build-base openssl-dev libffi-dev && \
       rm -rf /var/cache/apk/

COPY --chown=nobody:users base /app/base
COPY --chown=nobody:users k8sobjects /app/k8sobjects
COPY --chown=nobody:users check_kubernetesd /app/check_kubernetesd

USER nobody
WORKDIR /app

ENTRYPOINT [ "/app/check_kubernetesd" ]
