FROM python:3.11
LABEL maintainer="operations@vico-research.com"
LABEL Description="zabbix-kubernetes - efficent kubernetes monitoring for zabbix"

MAINTAINER operations@vico-research.com

ENV K8S_API_HOST ""
ENV K8S_API_TOKEN ""
ENV ZABBIX_SERVER "zabbix"
ENV ZABBIX_HOST "k8s"
ENV CRYPTOGRAPHY_DONT_BUILD_RUST "1"

WORKDIR /app
COPY --chown=nobody:users Pipfile  /app/

RUN  apt-get update -y
RUN  apt-get upgrade -y
RUN  apt-get dist-upgrade -y
RUN  apt-get install libffi-dev libffi8 libssl-dev bash screen ncdu -y
RUN  pip install --root-user-action=ignore --upgrade pip && pip install --root-user-action=ignore pipenv
RUN  PIPENV_USE_SYSTEM=1 pipenv install --skip-lock --system
RUN  apt-get remove base libssl-dev libffi-dev gcc -y
RUN  apt-get autoremove -y
RUN  rm -rf /var/lib/apt/lists/* /root/.cache

COPY --chown=nobody:users base /app/base
COPY --chown=nobody:users k8sobjects /app/k8sobjects
COPY --chown=nobody:users check_kubernetesd /app/check_kubernetesd
COPY --chown=nobody:users config_default.ini /app/config_default.ini

USER nobody
ENTRYPOINT [ "/app/check_kubernetesd" ]
