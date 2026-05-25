# GACHI-AI 배포 가이드

## Docker image 태그

- `develop` push: `<DOCKERHUB_USERNAME>/gachi-ai:develop`, `<DOCKERHUB_USERNAME>/gachi-ai:sha-xxxxxxx`
- `main` push: `<DOCKERHUB_USERNAME>/gachi-ai:latest`, `<DOCKERHUB_USERNAME>/gachi-ai:sha-xxxxxxx`

## GitHub Actions secrets

Docker image build/push에 필요합니다.

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

EC2 배포에 필요합니다.

- `EC2_INSTANCE_ID`
- `AWS_REGION`
- `AWS_OIDC_ROLE_ARN` 또는 `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
- 선택: `AWS_SESSION_TOKEN`
- 선택: `EC2_DEPLOY_PATH` 기본값은 `/home/ubuntu/GACHI-BE/deploy`

## 배포 방식

AI 서버는 별도 EC2를 만들지 않고 기존 백엔드 EC2의 compose 파일에 정의된 `ai` 서비스로 배포합니다.

`main` push에서 `AI Docker CI`가 성공하거나, `workflow_dispatch`로 `deploy-ai-ec2.yml`을 직접 실행하면 다음 작업을 수행합니다.

1. EC2의 deploy path로 이동
2. `.env`의 `AI_IMAGE`를 `<DOCKERHUB_USERNAME>/gachi-ai:latest`로 갱신
3. `docker compose --env-file .env pull ai`
4. `ai` 컨테이너 재생성
5. `ai` health check 확인
6. 필요 시 `nginx` 재생성

## 수동 확인

```bash
cd /home/ubuntu/GACHI-BE/deploy
docker compose --env-file .env ps
curl -i http://localhost:8000/ai/health
curl -i http://localhost/ai/health
```
