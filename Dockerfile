FROM python:3.9
LABEL maintainer="ms-github@256bit.org"
LABEL Description="zabbix-kubernetes - efficent kubernetes monitoring for zabbix"

MAINTAINER operations@vico-research.com

ENV K8S_API_HOST ""
ENV K8S_API_TOKEN ""
ENV ZABBIX_SERVER "zabbix"
ENV ZABBIX_HOST "k8s"
ENV CRYPTOGRAPHY_DONT_BUILD_RUST "1"

COPY --chown=nobody:users requirements.txt /app/requirements.txt

RUN  apt-get update -y && \
       apt-get install libffi-dev libffi7 libssl-dev bash screen ncdu -y && \
       pip3 install --upgrade pip && \
       pip3 install -r /app/requirements.txt && \
       apt-get upgrade -y && \
       apt-get dist-upgrade -y  && \
       apt-get remove base libssl-dev libffi-dev gcc -y && \
       apt-get autoremove -y && \
       rm -rf /var/lib/apt/lists/* /root/.cache

COPY --chown=nobody:users base /app/base
COPY --chown=nobody:users k8sobjects /app/k8sobjects
COPY --chown=nobody:users check_kubernetesd /app/check_kubernetesd

USER nobody
WORKDIR /app

ENTRYPOINT [ "/app/check_kubernetesd" ]
