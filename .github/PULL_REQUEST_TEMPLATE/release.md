## 📌 작업 요약

- 요약:
  - develop 브랜치의 누적 변경사항을 main으로 릴리즈 배포
- 관련 이슈: closes #

## 🌿 브랜치 정보

- **Source**: `develop` (기본)
- **Target**: `main` (릴리즈)

## ✅ 체크리스트

- [ ] 브랜치 컨벤션 준수 (`feat/refac/hotfix/chore/design/bugfix`)
- [ ] 커밋 컨벤션 준수 (`feat/fix/refactor/docs/style/chore`)
- [ ] self-review 완료
- [ ] 테스트 및 로컬 실행 확인 완료

## 🧪 테스트 결과

- GitHub Actions `deploy-ec2` 실행 확인 (`workflow_dispatch`, ref: `main`)
  - 결과:
  - 스크린샷: ![ssm-send-step]()

- 원격 배포 순서/재기동 확인
  - 결과:
  - 스크린샷: ![ssm-order]()

- 배포 후 컨테이너 상태 확인
  - 결과:
  - 스크린샷: ![compose-ps]()
