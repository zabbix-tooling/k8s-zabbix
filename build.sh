#!/bin/bash

####################################################################
## Helpers

notice(){
   echo -e "\e[1;32m$1\e[0m"
}

# Parameter:
#   1: cmd
# Execute simple shell command, exit if errorcode of shell command != 0
exec_cmd(){
   local CMD="$1"
   echo "+ $CMD"
   eval "$CMD 2>&1"
   local RET="$?"
   if [ "$RET" != "0" ];then
      echo "ERROR: execution failed (returncode $RET)"
      exit 2
   fi
   return 0
}

get_env(){
   echo -n "--env ZABBIX_SERVER=localhost "
   echo -n "--env ZABBIX_HOST=localhost "
   echo -n "--env K8S_CONFIG_TYPE=token "
}
####################################################################
## MAIN

DEFAULT_PHASES="build_image cleanup docu test_container"

VERSION="${VERSION:-$(git describe --abbrev=0 --tags)}"
TIMESTAMP="$(date --date="today" "+%Y%m%d%H%M%S")"

DOCKER_SQUASH="${DOCKER_SQUASH:-true}"

DELAY="35"

BDIR="$(dirname $(readlink -f $0))"
cd $BDIR || exit 1

# PHASES
build_image(){
   if [ -z "$VERSION" ];then
      echo "ERROR: no git release tag available"
      exit 1
   fi
   if [ "$DOCKER_SQUASH" == "true" ];then
      SQUASH_OPT="--squash"
      notice "Squashing of image is enabled, you can disable that by 'export DOCKER_SQUASH=false'"
   else
      SQUASH_OPT=""
   fi

   exec_cmd "docker build $SQUASH_OPT -t ${IMAGE_BASE} -f Dockerfile ."
   SIZE="$(docker inspect $IMAGE_BASE --format='{{.Size}}')"
   notice "Image size $(( $SIZE / 1024 / 1024 ))MB"
}

test_container(){
   IDENT="${IMAGE_NAME}_test"
   docker kill $IDENT &> /dev/null
   docker rm $IDENT &> /dev/null
   exec_cmd "docker run --rm $(get_env) -d --name $IDENT ${IMAGE_BASE}"
   sleep 10
   echo "====== DOCKER LOGS"
   docker logs --until=50s $IDENT
   echo "=================="
   exec_cmd "docker ps |grep $IDENT"
   exec_cmd "docker kill $IDENT"
}


inspect(){
   IDENT="${IMAGE_NAME}_test"
   exec_cmd "docker run -ti --rm $(get_env) --name $IDENT ${IMAGE_BASE} /bin/sh"
}


cleanup(){
  exec_cmd "rm -rf /tmp/${IMAGE_NAME}*"
  exec_cmd "docker rmi ${IMAGE_NAME} --force"
}

docu(){
   exec_cmd "template/create_template_documentation"
}

publish_image(){
  TIMESTAMP="$(date --date="today" "+%Y-%m-%d_%H-%M-%S")"
  exec_cmd "docker tag ${IMAGE_REPO}/${IMAGE_NAME}:${VERSION} ${IMAGE_REPO}/${IMAGE_NAME}:${VERSION}"
  exec_cmd "docker push ${IMAGE_REPO}/${IMAGE_NAME}:${VERSION}"
  exec_cmd "docker tag ${IMAGE_REPO}/${IMAGE_NAME}:${VERSION} ${IMAGE_REPO}/${IMAGE_NAME}:latest"
  exec_cmd "docker push ${IMAGE_REPO}/${IMAGE_NAME}:latest"
}

display_hint(){
  notice "CMD:"
  echo
  echo "$0 <phase>..<phase> <dockerhub repo_name>"
  echo
  notice "AVAILABLE PHASES:"
  echo  " -  default"
  echo  "    ($DEFAULT_PHASES)"
  echo  " -  inspect"
  for PHASE in $DEFAULT_PHASES; do
    echo " -  $PHASE <repo_name>"
  done
  echo " -  publish_image (optional)"
  echo " -  inspect (optional)"
}


if [ ${#@} -lt 2 ];then 
  display_hint
  exit 2
fi

IMAGE_REPO="${@: -1}"
if type $IMAGE_REPO &>/dev/null;then
   echo "ERROR: last param is not the dockerhub repo"
   exit 1
fi

PHASES=""
for arg in "${@:1:$(( ${#@} - 1 ))}"; do
   if [ "$arg" = "default" ];then
      PHASES="$PHASES $DEFAULT_PHASES"
   else
      PHASES="$PHASES $arg"
   fi
done

IMAGE_NAME="k8s-zabbix"
IMAGE_BASE="${IMAGE_REPO}/${IMAGE_NAME}:${VERSION}"

for PHASE in $PHASES;
do
   if ( type "$PHASE" >/dev/null 2>&1 );then
      notice "INFO: PHASE >>>$PHASE<<< for $IMAGE_BASE"
      $PHASE
   else
      notice "ERROR: no such phase : $PHASE"
      exit 1
   fi
done

#SIZE="$(docker inspect $IMAGE_BASE --format='{{.Size}}')"
#notice "Image size $(( $SIZE / 1024 / 1024 ))MB"
notice "SUCESSFULLY COMPLETED"
