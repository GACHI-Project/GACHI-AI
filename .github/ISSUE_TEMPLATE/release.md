---
name: "Release"
about: "develop → main 릴리즈 체크리스트"
title: "[TASK] 릴리즈 배포: develop → main"
---

## 🎯 목적

develop 브랜치에 누적된 변경사항을 main으로 릴리즈 배포합니다.

## 📦 포함 범위

- **포함 이슈**
- #

- **포함 PR**
- #

- **제외 이슈**
- #

- **제외 PR**
- #

## ✅ 릴리즈 체크리스트

- [ ] develop 최신 상태 확인
- [ ] release PR 생성 (develop → main)
- [ ] 리뷰/체크 통과
- [ ] main 머지
- [ ] deploy-ec2 수동 실행 (workflow_dispatch, ref: main)
- [ ] 배포 검증 완료 (ssm-send-step, ssm-order, compose-ps)
