# GACHI-AI Deploy Guide

## 1) 이미지 태그 규칙
- `develop` 브랜치 push: `<DOCKERHUB_USERNAME>/gachi-ai:develop`, `sha-<7자리>`
- `main` 브랜치 push: `<DOCKERHUB_USERNAME>/gachi-ai:latest`, `sha-<7자리>`

## 2) GitHub Actions 필수 시크릿
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

## 3) EC2 반영 (BE compose에서 함께 기동)

### develop 반영
```bash
cd ~/GACHI-BE/deploy
sed -i 's|^AI_IMAGE=.*|AI_IMAGE=<DOCKERHUB_USERNAME>/gachi-ai:develop|' .env
docker compose --env-file .env pull ai
docker compose --env-file .env up -d --force-recreate ai nginx
```

### main 반영
```bash
cd ~/GACHI-BE/deploy
sed -i 's|^AI_IMAGE=.*|AI_IMAGE=<DOCKERHUB_USERNAME>/gachi-ai:latest|' .env
docker compose --env-file .env pull ai
docker compose --env-file .env up -d --force-recreate ai nginx
```

## 4) 상태 확인
```bash
docker compose --env-file .env ps
curl -i http://localhost/ai/health
curl -i http://localhost/ai/docs
```

## 5) 롤백
```bash
cd ~/GACHI-BE/deploy
sed -i 's|^AI_IMAGE=.*|AI_IMAGE=<DOCKERHUB_USERNAME>/gachi-ai:sha-<원하는태그>|' .env
docker compose --env-file .env pull ai
docker compose --env-file .env up -d --force-recreate ai nginx
```
