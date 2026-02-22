pipeline {
    agent any

    environment {
        DOCKER_IMAGE = 'atdon/interview_latest'
        DOCKER_TAG   = "${env.BUILD_NUMBER}"
        DOCKERHUB    = credentials('dockerhub-creds')  // Jenkins credential ID
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Security Scan - SAST') {
            steps {
                sh '''
                    pip install bandit safety
                    bandit -r app/ -f json -o bandit-report.json --exit-zero
                    safety check -r app/requirements.txt || true
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'bandit-report.json', allowEmptyArchive: true
                }
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    pip install flake8
                    flake8 app/ --max-line-length=120 --exit-zero
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh "docker build -t ${DOCKER_IMAGE}:${DOCKER_TAG} ./app"
            }
        }

        stage('Container Security Scan - Trivy') {
            steps {
                sh """
                    docker run --rm \
                      -v /var/run/docker.sock:/var/run/docker.sock \
                      aquasec/trivy:latest image \
                      --severity HIGH,CRITICAL \
                      --exit-code 0 \
                      ${DOCKER_IMAGE}:${DOCKER_TAG}
                """
            }
        }

        stage('Push to DockerHub') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    echo "$DOCKERHUB_PSW" | docker login -u "$DOCKERHUB_USR" --password-stdin
                    docker tag ${DOCKER_IMAGE}:${DOCKER_TAG} ${DOCKER_IMAGE}:latest
                    docker push ${DOCKER_IMAGE}:${DOCKER_TAG}
                    docker push ${DOCKER_IMAGE}:latest
                '''
            }
        }

        stage('Terraform Validate') {
            steps {
                dir('terraform') {
                    sh '''
                        terraform init -backend=false
                        terraform fmt -check
                        terraform validate
                    '''
                }
            }
        }

        stage('Deploy to EC2') {
            when {
                branch 'main'
            }
            steps {
                sshagent(['ec2-ssh-key']) {
                    sh '''
                        ssh -o StrictHostKeyChecking=no ubuntu@${EC2_HOST} << 'EOF'
                            cd /opt/app
                            docker compose pull
                            docker compose up -d --force-recreate
                            docker system prune -f
EOF
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker system prune -f || true'
        }
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed. Check logs above.'
        }
    }
}
