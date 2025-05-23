#!groovy

pipeline {
    agent any
    parameters {
        booleanParam(defaultValue: false, description: 'Create release', name: 'RELEASE')
        string(name: 'REPO', defaultValue: '-', description: 'Repo for docker')
    }

    triggers {
        cron('@daily')
        pollSCM('H/15 * * * *')
    }

    options{
         buildDiscarder(logRotator(artifactDaysToKeepStr: '10', artifactNumToKeepStr: '10', daysToKeepStr: '3', numToKeepStr: '20'))
         disableConcurrentBuilds()
    }

    stages {
        stage('Prepare') {
            when {
                  environment name: 'RELEASE', value: 'true'
            }
            steps {
               ansiColor('xterm') {
                  sh 'git fetch --tags'
                  sh "./build.sh cleanup ${params.TARGET}"
               }
            }
        }
        stage('Build and Test') {
            steps {
                ansiColor('xterm') {
                  sh 'git fetch --tags'
                  sh "./build.sh default ${params.TARGET}"
                }
            }
        }
        stage('Release') {
            when {
                  environment name: 'RELEASE', value: 'true'
            }
            steps {
               ansiColor('xterm') {
                  sh "./build.sh publish_image ${params.TARGET}"
               }
            }
        }
   }

}
