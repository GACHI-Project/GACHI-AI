import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# CI의 pytest 수집 환경에서도 app 패키지를 항상 프로젝트 루트 기준으로 찾게 한다.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
