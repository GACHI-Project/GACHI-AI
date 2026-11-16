# GACHI-AI 배포 가이드

## 이미지 게시

`AI Docker CI`가 `develop` 또는 `main`에서 성공하면 GitHub Container Registry에 이미지를 게시합니다. 이미지 주소는 `ghcr.io/gachi-project/gachi-ai`입니다.

- `develop` push: `develop`, `sha-<전체 커밋 SHA>`
- `main` push: `latest`, `sha-<전체 커밋 SHA>`

이미지 게시에는 워크플로의 `GITHUB_TOKEN`을 사용하며 `packages: write` 권한이 필요합니다. 최초 게시 후 저장소의 **Packages**에서 `gachi-ai` 패키지가 연결되었는지 확인합니다. 패키지가 비공개라면 EC2가 읽을 수 있는 토큰이 필요합니다.

## 배포 전 설정

GitHub Actions secrets:

- `EC2_INSTANCE_ID`
- `AWS_REGION`
- `AWS_OIDC_ROLE_ARN` 또는 `AWS_ACCESS_KEY_ID`와 `AWS_SECRET_ACCESS_KEY`
- `GHCR_USERNAME`: 아래 읽기 토큰을 발급한 GitHub 사용자 이름
- 선택: `AWS_SESSION_TOKEN`
- 선택: `EC2_DEPLOY_PATH`, 기본값 `/home/ubuntu/GACHI-BE/deploy`
- 선택: `GHCR_TOKEN_PARAMETER_NAME`, 기본값 `/gachi/prod/ghcr/ai-token`

EC2가 GHCR의 비공개 패키지를 읽도록 다음을 준비합니다.

1. `read:packages` 권한이 있고 `gachi-ai` 패키지를 읽을 수 있는 GitHub 토큰을 발급합니다. 조직 또는 패키지 접근 설정에서 해당 사용자의 권한도 확인합니다.
2. 토큰을 AWS Systems Manager Parameter Store에 `SecureString`으로 저장합니다. 이름은 기본값 `/gachi/prod/ghcr/ai-token`을 사용하거나 `GHCR_TOKEN_PARAMETER_NAME`에 설정한 이름을 사용합니다.
3. EC2 인스턴스 역할에 해당 파라미터의 `ssm:GetParameter` 권한을 부여합니다. 고객 관리형 KMS 키로 암호화했다면 해당 키의 `kms:Decrypt` 권한도 필요합니다.

토큰 값은 GitHub Actions의 SSM 명령에 포함하지 않습니다. EC2에서 파라미터를 읽어 GHCR에 로그인하고 이미지를 pull합니다. Docker 인증 파일은 임시 디렉터리에 두고 명령 종료 시 삭제합니다. 이 설정은 기존 백엔드 이미지의 인증 설정에 영향을 주지 않습니다.

## 배포 방식

AI 서버는 기존 백엔드 EC2의 compose 파일에 정의된 `ai` 서비스로 배포합니다. `main`에서 `AI Docker CI`가 성공하면 자동 배포합니다. `main` 브랜치에서 `Deploy AI to EC2`를 수동 실행할 수도 있습니다. 이전 커밋의 CI가 늦게 완료되면 현재 `main` 커밋과 비교하여 배포를 건너뜁니다.

1. 대상 커밋의 `ghcr.io/gachi-project/gachi-ai:sha-<전체 커밋 SHA>` 이미지를 EC2에서 pull합니다.
2. pull에 성공하면 배포 디렉터리 `.env`의 `AI_IMAGE`만 갱신합니다. `BACKEND_IMAGE`는 변경하지 않습니다.
3. `ai` 컨테이너를 재생성하고 헬스 체크와 실행 중인 이미지 태그를 확인합니다.
4. `nginx`를 재생성합니다.

이미지 pull에 실패하면 기존 `.env`의 `AI_IMAGE` 값은 유지됩니다. 수동 배포는 `main`의 커밋을 대상으로 하며, 해당 커밋의 이미지가 GHCR에 게시되어 있어야 합니다.

## GitHub Deployments 확인

저장소의 **Deployments** 화면에서 `production` 환경을 선택하면 배포 커밋과 상태를 확인할 수 있습니다. 배포 항목의 **View logs** 링크는 해당 Actions 실행 기록으로 연결됩니다. 자동 배포에는 성공한 `AI Docker CI`의 대상 커밋이, 수동 배포에는 `main`에서 실행한 커밋이 기록됩니다.

배포 확인 시 Deployments의 커밋 SHA를 복사한 다음 저장소 **Packages**의 `gachi-ai`에서 `sha-<전체 커밋 SHA>` 태그를 찾습니다. 아래 `docker inspect` 결과의 이미지 주소와 태그도 같은지 대조합니다.

SSM 명령, `ai` 헬스 체크, 이미지 태그 확인, nginx 재생성이 모두 성공해야 배포 상태가 `success`가 됩니다. 실패하면 `failure`로 기록합니다. Actions 실행이 취소되어 SSM 결과를 확인할 수 없으면 `error`로 기록합니다.

## 수동 확인

```bash
cd /home/ubuntu/GACHI-BE/deploy
grep '^AI_IMAGE=' .env
docker compose --env-file .env ps
docker inspect --format '{{.Config.Image}}' "$(docker compose --env-file .env ps -q ai)"
curl -i http://localhost:8000/ai/health
curl -i http://localhost/ai/health
```
