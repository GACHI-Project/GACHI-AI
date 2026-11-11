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

`main`에서 `AI Docker CI`가 성공하거나, `main` 브랜치에서 `workflow_dispatch`로 `deploy-ai-ec2.yml`을 직접 실행하면 다음 작업을 수행합니다. 이전 커밋의 CI가 늦게 완료되면 현재 `main` 커밋과 비교하여 배포를 건너뜁니다.

1. EC2의 deploy path로 이동
2. 대상 커밋의 `<DOCKERHUB_USERNAME>/gachi-ai:sha-xxxxxxx` 이미지를 pull
3. pull에 성공하면 `.env`의 `AI_IMAGE`를 해당 이미지로 갱신
4. `ai` 컨테이너 재생성
5. `ai` health check 확인
6. `nginx` 재생성

이미지 pull에 실패하면 기존 `.env`의 `AI_IMAGE` 값을 유지합니다. 수동 배포는 `main`의 커밋을 대상으로 하며, 해당 커밋의 이미지가 Docker Hub에 게시되어 있어야 합니다.

## GitHub Deployments 확인

저장소의 **Deployments** 화면에서 `production` 환경을 선택하면 배포 커밋과 상태를 확인할 수 있습니다. 배포 항목의 **View logs** 링크는 해당 Actions 실행 기록으로 연결됩니다. 자동 배포에는 성공한 `AI Docker CI`의 대상 커밋이, 수동 배포에는 `main`에서 실행한 커밋이 기록됩니다.

SSM 명령과 `ai` 헬스 체크, nginx 재생성이 모두 성공해야 배포 상태가 `success`가 됩니다. 실패하면 `failure`로 기록합니다. Actions 실행이 취소되어 SSM 결과를 확인할 수 없으면 결과가 불명확하다는 뜻의 `error`로 기록합니다.

## 수동 확인

```bash
cd /home/ubuntu/GACHI-BE/deploy
docker compose --env-file .env ps
curl -i http://localhost:8000/ai/health
curl -i http://localhost/ai/health
```
